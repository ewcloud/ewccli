#!/usr/bin/env bash
set -euo pipefail

# NOTE: For tracking status and graceful failure
EWCCLI_STATUS="failing"
GREEN_LIGHT="🟢"
RED_LIGHT="🔴"

# NOTE: Only needed to cleanup Floating IPs via OpenStack CLI, as the EWCCLI cannot
export OS_AUTH_TYPE=v3applicationcredential
export OS_INTERFACE=public
export OS_IDENTITY_API_VERSION=3

# --- Step 1 --- 
echo "Clone catalog repository (ref: '${CATALOG_REF}')"
PATH_TO_CATALOG_REPO="${GITHUB_WORKSPACE}/ewc-community-hub"
git clone \
  --depth 1 \
  --branch "${CATALOG_REF}" \
  "https://github.com/ewcloud/ewc-community-hub.git" \
  "${PATH_TO_CATALOG_REPO}"

# --- Step 2 --- 
echo "Extract metadata of '${ITEM_NAME}' from catalog"
PATH_TO_CATALOG="${PATH_TO_CATALOG_REPO}/items.yaml"
item_metadata=$(yq '.spec.items."'"$ITEM_NAME"'" | del(.description)' $PATH_TO_CATALOG) # Drop the description attribute(for succinct step summary)

if [[ "${item_metadata}" == "null" ]]; then
  echo "::error::Item '${ITEM_NAME}' not found in catalog repository (ref: '${CATALOG_REF}')"
  exit 1
fi

# --- Step 3 ---
echo "Validate input spec format"
if [ -z "${INPUT_SPEC_JSON}" ]; then
  INPUT_SPEC_JSON="{}"
fi
if ! printf "%s" "${INPUT_SPEC_JSON}" | jq -e . >/dev/null 2>&1; then
  echo "::error::inputSpecJson is invalid JSON. Got: '$INPUT_SPEC_JSON'"
  exit 1
fi

EXTRA_VARS=""
if [[ "${INPUT_SPEC_JSON}" != "{}" ]]; then
  # Any inputs, defined at runtime, are converted to match EWCCLI's fingerprint:
  #  ```txt
  #  --item-input x=1 --item-input y=2 ...
  #  ```
  #  NOTE: Special complexity is added due to single quotation required around values of type array and object.
  #        We rely on the unicode of single quote characters to avoid jq compilation errors (i.e. "\u0027" -> "'")
  EXTRA_VARS=$(printf "%s" "${INPUT_SPEC_JSON}" | jq -r '
    to_entries[]
    | "--item-input " + .key + "=" +
      if .value == null then 
        "None"
      elif (.value | type) == "array" or (.value | type) == "object" then
        "\u0027" + (.value | tojson) + "\u0027"
      else
        .value | tostring
      end
      + " \\"
    '
  )
  EXTRA_VARS="${EXTRA_VARS:0:-1}" # Remove the last trailing slash of the concatenated vars ("\")
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
echo "Setup SSH private and public keys"
mkdir -p /tmp/.ssh
chmod 700 "/tmp/.ssh"
ANSIBLE_SSH_PRIVATE_KEY_FILE="/tmp/.ssh/id_github_ewccli"
ANSIBLE_SSH_PUBLIC_KEY_FILE="/tmp/.ssh/id_github_ewccli.pub"
printf "%s" "$ANSIBLE_SSH_PRIVATE_KEY" > "$ANSIBLE_SSH_PRIVATE_KEY_FILE"
printf "%s" "$ANSIBLE_SSH_PUBLIC_KEY" > "$ANSIBLE_SSH_PUBLIC_KEY_FILE"
chmod 600 "$ANSIBLE_SSH_PRIVATE_KEY_FILE"
chmod 600 "$ANSIBLE_SSH_PUBLIC_KEY_FILE"

export EWC_CLI_SSH_PUBLIC_KEY_PATH=$ANSIBLE_SSH_PUBLIC_KEY_FILE
export EWC_CLI_SSH_PRIVATE_KEY_PATH=$ANSIBLE_SSH_PRIVATE_KEY_FILE

# --- Step 7 --- 
echo "Login"

EWCCLI_LOGIN_EXIT_CODE=0
EWCCLI_LOGIN_CMD=(ewc login)
set +e
"${EWCCLI_LOGIN_CMD[@]}"
EWCCLI_LOGIN_EXIT_CODE=$?
set -e

# --- Step 8 --- 
echo "Deploy (including VM provisioning)"

if [ -z "${EXTRA_VARS}" ]; then 
  EWCCLI_DEPLOY_CMD=(ewc hub --path-to-catalog "${PATH_TO_CATALOG}" deploy "${ITEM_NAME}" --server-name "github-vm-${GITHUB_RUN_ID}" --external-ip)
else
  EWCCLI_DEPLOY_CMD=(ewc hub --path-to-catalog "${PATH_TO_CATALOG}" deploy "${ITEM_NAME}" --server-name "github-vm-${GITHUB_RUN_ID}" --external-ip "${EXTRA_VARS}")
fi

EWCCLI_DEPLOY_EXIT_CODE=0
set +e
"${EWCCLI_DEPLOY_CMD[@]}"
EWCCLI_DEPLOY_EXIT_CODE=$?
set -e

# --- Step 9 --- 
echo "Cleanup"

EWCCLI_CLEANUP_EXIT_CODE=0
EWCCLI_CLEANUP_CMD=(ewc infra delete "github-vm-${GITHUB_RUN_ID}")
set +e
"${EWCCLI_CLEANUP_CMD[@]}"
EWCCLI_CLEANUP_EXIT_CODE=$?
set -e

if [ "${EWCCLI_LOGIN_EXIT_CODE}" -eq 0 ] && [ "${EWCCLI_DEPLOY_EXIT_CODE}" -eq 0 ] && [ "${EWCCLI_CLEANUP_EXIT_CODE}" -eq 0 ]; then
  EWCCLI_STATUS="passing"
fi

# --- Step 10 ---
echo "Collect artifacts"
pip freeze > "$ARTIFACTS_DIR/requirements.txt"

printf "%s" "{\"ewccli_login_exit_code\":\"$EWCCLI_LOGIN_EXIT_CODE\"}" > "$ARTIFACTS_DIR/ewccli_login_exit_code.json"
printf "%s" "{\"ewccli_deploy_exit_code\":\"$EWCCLI_DEPLOY_EXIT_CODE\"}" > "$ARTIFACTS_DIR/ewccli_deploy_exit_code.json"
printf "%s" "{\"ewccli_cleanup_exit_code\":\"$EWCCLI_DEPLOY_EXIT_CODE\"}" > "$ARTIFACTS_DIR/ewccli_cleanup_exit_code.json"
printf "%s" "${item_metadata}" > "$ARTIFACTS_DIR/item_metadata.yaml"
echo "${EWCCLI_LOGIN_CMD[@]}" > "$ARTIFACTS_DIR/login.sh"
echo "${EWCCLI_DEPLOY_CMD[@]}" > "$ARTIFACTS_DIR/deploy.sh"
echo "${EWCCLI_CLEANUP_CMD[@]}" > "$ARTIFACTS_DIR/cleanup.sh"

# --- Step 11 ---
echo "Write execution summary"
add_summary() {
  # NOTE: Helper for appending markdown
  printf "%s\n" "$1" >> "$GITHUB_STEP_SUMMARY"
}

add_summary "# EWC Community Hub EWCCLI - Ansible Deployment Test Summary"
add_summary ""
add_summary "- **Run ID:** \`${GITHUB_RUN_ID}\`"
add_summary "- **Repository:** \`${GITHUB_REPOSITORY}\`"
add_summary "- **Branch/Tag:** \`${GITHUB_REF_NAME}\`"
add_summary "- **Entrypoint:** \`ewc hub deploy ${ITEM_NAME}\`"
add_summary ""
add_summary "## Status"
add_summary "### Application Execution"
if [ "${EWCCLI_LOGIN_EXIT_CODE}" -eq 0 ] && [ "${EWCCLI_DEPLOY_EXIT_CODE}" -eq 0 ] && [ "${EWCCLI_CLEANUP_EXIT_CODE}" -eq 0 ]; then
  add_summary "- **EWCCLI Status:** \`passing\` ${GREEN_LIGHT}"
else
  add_summary "- **EWCCLI Status:** \`failing\` ${RED_LIGHT}"
fi
add_summary "- **EWCCLI Exit Code:** \`${EWCCLI_DEPLOY_EXIT_CODE}\`"
add_summary ""
add_summary "## Environment Details"
add_summary "### Prerequisites"
add_summary "- \`$PYTHON_VERSION\`"
add_summary "- \`$ANSIBLE_VERSION\`"
add_summary "- \`$OPENSTACK_VERSION\`"
add_summary "### Item"
add_summary "\`\`\`yaml"
cat "$ARTIFACTS_DIR/item_metadata.yaml" >> "$GITHUB_STEP_SUMMARY"
add_summary ""
add_summary "\`\`\`"
add_summary ""
add_summary "### Execution Plan"
add_summary "\`\`\`bash"
cat "$ARTIFACTS_DIR/login.sh" >> "$GITHUB_STEP_SUMMARY"
add_summary ""
add_summary "\`\`\`"
add_summary ""
add_summary "\`\`\`bash"
cat "$ARTIFACTS_DIR/deploy.sh" >> "$GITHUB_STEP_SUMMARY"
add_summary ""
add_summary "\`\`\`"
add_summary ""
add_summary "\`\`\`bash"
cat "$ARTIFACTS_DIR/cleanup.sh" >> "$GITHUB_STEP_SUMMARY"
add_summary ""
add_summary "\`\`\`"
add_summary ""
add_summary "---"
add_summary "_Summary Auto-generated by \"EWCCLI Test Deploy\" GitHub Action_"

cp $GITHUB_STEP_SUMMARY "$ARTIFACTS_DIR/summary.md"

# --- Step 12 ---
# NOTE: As of 18.02.2026, this is needed for cleaning up any created Floating IPs, since the EWCCLI does not remove them and is unclear if it reuses existing consistently
echo "Unlocking the Floating IP (best-effort approach)"
floating_ip=$(openstack server show "github-vm-${GITHUB_RUN_ID}" -f json | jq '.addresses[].[] | select( (startswith("192.") or startswith("10.")) | not )' | tr -d '"' ) || true
openstack floating ip delete $floating_ip || true 

# --- Step 13 --- 
echo "Re-rasing test errors (if any)"
if [ "$EWCCLI_STATUS" = "failing" ]; then
  echo "::error::One or more failures caught during testing. See the summary or logs for details"
  exit 1
fi
