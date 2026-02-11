#!/usr/bin/env bash
set -euo pipefail

# NOTE: For tracking status and graceful failure
EWCCLI_STATUS="failing"
GREEN_LIGHT="🟢"
RED_LIGHT="🔴"

# --- Step 1 --- 
echo "Clone catalog repository (ref: '${CATALOG_REF}')"
PATH_TO_CATALOG_REPO=".tmp/ewc-community-hub"
git clone \
  --depth 1 \
  --branch "${CATALOG_REF}" \
  "https://github.com/ewcloud/ewc-community-hub.git" \
  "${PATH_TO_CATALOG_REPO}"

# --- Step 2 --- 
echo "Resolve item '${ITEM_NAME}' from catalog"
PATH_TO_CATALOG="${PATH_TO_CATALOG_REPO}/items.yaml"
item_metadata=$(yq '.spec.items."'"$ITEM_NAME"'" | del(.description)' $PATH_TO_CATALOG) # Ignores description, for the sake of having succinct summaries

if [[ "${item_metadata}" == "null" ]]; then
  echo "::error::Item '${ITEM_NAME}' not found in catalog repository (ref: '${CATALOG_REF}')"
  exit 1
fi

# --- Step 3 ---
echo "Validate input spec format"
if [ -n "$INPUT_SPEC_JSON" ]; then
  echo "::warning::Workflow input 'inputSpecJson' will override Item inputs defined in the catalog"
else
  input_spec=$(printf "%s" "${item_metadata}" | yq '.values.inputSpec[] // [] | select( has("default") and .default != "None" )') # Ignores inputs without default values or None values

  if [[ "${input_spec}" == "null" ]]; then
    INPUT_SPEC_JSON="{}"
  else
    INPUT_SPEC_JSON=$(printf "%s" "${input_spec}" | yq '.inputSpec' -o=json | jq 'map(select(.name and .default) | {(.name): .default}) | add // {}' )
  fi
fi

if ! printf "%s" "$INPUT_SPEC_JSON" | jq -e . >/dev/null 2>&1; then
  echo "::error::inputSpecJson is invalid JSON. Got: '$INPUT_SPEC_JSON'"
  exit 1
fi

# --- Step 4 ---
echo "Gather environment facts"
PYTHON_VERSION="$(python3 --version)"
ANSIBLE_VERSION="$(pip freeze | grep 'ansible' | awk -F'==' '{print $1, $2}')"
OPENSTACK_VERSION="$(pip freeze | grep 'openstack' | awk -F'==' '{print $1, $2}')"

# --- Step 5 ---
echo "Create artifact directory"
ARTIFACTS_DIR="${GITHUB_WORKSPACE}/artifacts"
mkdir -p "$ARTIFACTS_DIR"

# --- Step 6 ---
echo "Write out extra vars"
EXTRA_VARS=$(printf "%s" "$INPUT_SPEC_JSON" | jq -r 'to_entries | map("--item-inputs \(.key)=\(.value)") | join(" ")')

# --- Step 7 ---
echo "Setup SSH private and public keys"
mkdir -p /tmp/.ssh
chmod 700 "/tmp/.ssh"
ANSIBLE_SSH_PRIVATE_KEY_FILE="/tmp/.ssh/id_github_ewccli"
ANSIBLE_SSH_PUBLIC_KEY_FILE="/tmp/.ssh/id_github_ewccli.pub"
printf "%s" "$ANSIBLE_SSH_PRIVATE_KEY" > "$ANSIBLE_SSH_PRIVATE_KEY_FILE"
printf "%s" "$ANSIBLE_SSH_PUBLIC_KEY" > "$ANSIBLE_SSH_PUBLIC_KEY_FILE"
chmod 600 "$ANSIBLE_SSH_PRIVATE_KEY_FILE"
chmod 600 "$ANSIBLE_SSH_PUBLIC_KEY_FILE"

# --- Step 8 --- 
echo "Run EWCCLI"
EWCCLI_EXIT_CODE=0

EWCCLI_LOGIN_CMD=(ewc login --ssh-private-key-path "${ANSIBLE_SSH_PRIVATE_KEY_FILE}" --ssh-public-key-path "${ANSIBLE_SSH_PUBLIC_KEY_FILE}")
set +e
"${EWCCLI_LOGIN_CMD[@]}"
EWCCLI_EXIT_CODE=$?
set -e

if [ "$EWCCLI_EXIT_CODE" -eq 0 ]; then

  EWCCLI_DEPLOY_CMD=(ewc hub --path-to-catalog "${PATH_TO_CATALOG}" deploy "${ITEM_NAME}" --server-name "github-vm-${GITHUB_RUN_ID}" --external-ip "${EXTRA_VARS}")
  set +e
  "${EWCCLI_DEPLOY_CMD[@]}"
  EWCCLI_EXIT_CODE=$?
  set -e
else
  EWCCLI_DEPLOY_CMD=("")
fi

if [ "$EWCCLI_EXIT_CODE" -eq 0 ]; then
  EWCCLI_STATUS="passing"
fi

# --- Step 9 ---
echo "Collect artifacts"
pip freeze > "$ARTIFACTS_DIR/requirements.txt"

printf "%s" "{\"ewccli_exit_code\":\"$EWCCLI_EXIT_CODE\"}" > "$ARTIFACTS_DIR/ewccli_exit_code.json"
printf "%s" "${item_metadata}" > "$ARTIFACTS_DIR/item_metadata.yaml"
echo "${EWCCLI_LOGIN_CMD[@]}" > "$ARTIFACTS_DIR/login.sh"

if [[ -n "${EWCCLI_DEPLOY_CMD[@]}"  ]]; then
  echo "${EWCCLI_DEPLOY_CMD[@]}" > "$ARTIFACTS_DIR/deploy.sh"
fi

# --- Step 10 ---
echo "Write execution summary"
add_summary() {
  # NOTE: Helper for appending markdown
  printf "%s\n" "$1" >> "$GITHUB_STEP_SUMMARY"
}

add_summary "# EWC Community Hub EWCCLI Test Summary"
add_summary ""
add_summary "- **Run ID:** \`${GITHUB_RUN_ID}\`"
add_summary "- **Repository:** \`${GITHUB_REPOSITORY}\`"
add_summary "- **Branch/Tag:** \`${GITHUB_REF_NAME}\`"
add_summary "- **Entrypoint:** \`ewc hub deploy ${ITEM_NAME}\`"
add_summary ""
add_summary "## Status"
add_summary "### Application Execution"
if [[ "${EWCCLI_EXIT_CODE}" -eq 0 ]]; then
  add_summary "- **EWCCLI Status:** \`passing\` ${GREEN_LIGHT}"
else
  add_summary "- **EWCCLI Status:** \`failing\` ${RED_LIGHT}"
fi
add_summary "- **EWCCLI Exit Code:** \`${EWCCLI_EXIT_CODE}\`"
add_summary ""
add_summary "## Environment Details"
add_summary "### Prerequisites"
add_summary "- \`$PYTHON_VERSION\`"
add_summary "- \`$ANSIBLE_VERSION\`"
add_summary "- \`$OPENSTACK_VERSION\`"
add_summary "### Item"
add_summary "\`\`\`yaml"
cat "${ARTIFACTS_DIR}/item_metadata.yaml" >> "$GITHUB_STEP_SUMMARY"
add_summary ""
add_summary "\`\`\`"
add_summary ""
add_summary "### Execution Plan"
add_summary "\`\`\`bash"
cat "$ARTIFACTS_DIR/login.sh" >> "$GITHUB_STEP_SUMMARY"
add_summary ""
add_summary "\`\`\`"
add_summary ""
if [[ -e "$ARTIFACTS_DIR/deploy.sh" ]]; then
  add_summary "\`\`\`bash"
  cat "$ARTIFACTS_DIR/deploy.sh" >> "$GITHUB_STEP_SUMMARY"
  add_summary ""
  add_summary "\`\`\`"
  add_summary ""
fi
add_summary "---"
add_summary "_Summary Auto-generated by \"EWCCLI Test Deploy\" GitHub Action_"

cp $GITHUB_STEP_SUMMARY "$ARTIFACTS_DIR/summary.md"

# --- Step 11 --- 
echo "Re-rasing test errors (if any)"
if [ "$EWCCLI_STATUS" = "failing" ]; then
  echo "::error::One or more failures caught during testing. See the summary or logs for details"
  exit 1
fi
