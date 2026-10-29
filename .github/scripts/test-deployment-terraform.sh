#!/usr/bin/env bash
set -euo pipefail

# NOTE: For tracking status and graceful failure
EWCCLI_STATUS="failing"
GREEN_LIGHT="🟢"
RED_LIGHT="🔴"
GRAY_LIGHT = "⚫"

export OS_AUTH_TYPE=v3applicationcredential
export OS_INTERFACE=public
export OS_IDENTITY_API_VERSION=3

EWCCLI_HOME="${HOME}/.ewccli"
DEPLOYMENT_NAME="e2e-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
DRY_RUN_DEPLOYMENT_NAME="${DEPLOYMENT_NAME}-dry-run"
DEPLOYMENT_NAME_REGEX='^[a-z0-9][a-z0-9-]{0,62}$'

find_workspace() {
  # NOTE: Workspaces live in ~/.ewccli/terraform/<profile>/<item>/<deployment_name>/
  local matches
  matches="$(compgen -G "${EWCCLI_HOME}/terraform/*/${ITEM_NAME}/$1" || true)"
  if [[ -z "${matches}" ]]; then
    return 1
  fi
  printf "%s\n" "${matches}" | head -n 1
}

format_cmd() {
  # NOTE: Print a command that can be copy-pasted into a shell
  local arg formatted=()
  for arg in "$@"; do
    if [[ "${arg}" =~ ^[A-Za-z0-9_./:=@%+,-]+$ ]]; then
      formatted+=("${arg}")
    else
      formatted+=("${arg@Q}")
    fi
  done
  echo "${formatted[*]}"
}

find_managed_runtime() {
  # NOTE: The managed runtime lives in ~/.ewccli/bin/tofu/<version>/tofu
  local candidate
  for candidate in "${EWCCLI_HOME}"/bin/tofu/*/tofu; do
    if [[ -f "${candidate}" && -x "${candidate}" ]]; then
      printf "%s\n" "${candidate}"
      return 0
    fi
  done
  return 1
}

count_managed_resources() {
  local state_file="$1/terraform.tfstate"
  if [[ ! -f "${state_file}" ]]; then
    echo 0
    return 0
  fi
  jq '[.resources[]? | select(.mode == "managed") | .instances[]?] | length' "${state_file}"
}

run_step() {
  local step="$1"
  shift
  echo "::group::${step}"
  local exit_code=0
  "$@" || exit_code=$?
  echo "::endgroup::"
  STEP_RESULT["${step}"]="${exit_code}"
}

fallback_cleanup() {
  local workspace="$1"
  local runtime root_module var_file
  if ! runtime="$(find_managed_runtime)"; then
    echo "::warning::Fallback cleanup impossible: no managed OpenTofu runtime found"
    return 1
  fi
  root_module="${workspace}/source/${PATH_TO_MAIN_FILE}"
  local tofu_args=("-chdir=${root_module}" destroy -auto-approve -input=false)
  for var_file in "${workspace}"/*.tfvars.json; do
    if [[ -f "${var_file}" ]]; then
      tofu_args+=("-var-file=${var_file}")
    fi
  done
  local child_env=(
    "PATH=${PATH}"
    "HOME=${HOME}"
    "TF_IN_AUTOMATION=1"
    "TF_INPUT=0"
    "OS_AUTH_TYPE=v3applicationcredential"
    "OS_AUTH_URL=${OS_AUTH_URL:-}"
    "OS_APPLICATION_CREDENTIAL_ID=${OS_APPLICATION_CREDENTIAL_ID:-}"
    "OS_APPLICATION_CREDENTIAL_SECRET=${OS_APPLICATION_CREDENTIAL_SECRET:-}"
  )
  if [[ -n "${OS_REGION_NAME:-}" ]]; then
    child_env+=("OS_REGION_NAME=${OS_REGION_NAME}")
  fi
  env -i "${child_env[@]}" "${runtime}" "${tofu_args[@]}"
}

# --- Step 1 ---
echo "Check deployment name"
if [[ ! "${DEPLOYMENT_NAME}" =~ ${DEPLOYMENT_NAME_REGEX} ]] || [[ ! "${DRY_RUN_DEPLOYMENT_NAME}" =~ ${DEPLOYMENT_NAME_REGEX} ]]; then
  echo "::error::Deployment name '${DRY_RUN_DEPLOYMENT_NAME}' does not match '${DEPLOYMENT_NAME_REGEX}'"
  exit 1
fi

# --- Step 2 ---
echo "Check that no Terraform or OpenTofu runtime is preinstalled"
for runtime_name in tofu terraform; do
  if runtime_path="$(command -v "${runtime_name}")"; then
    echo "::error::'${runtime_name}' is preinstalled at '${runtime_path}'. Remove it, so that the EWCCLI-managed OpenTofu install is tested"
    exit 1
  fi
done
if [[ -n "${EWC_CLI_TF_BIN:-}" ]]; then
  echo "::error::EWC_CLI_TF_BIN is set. Unset it, so that the EWCCLI-managed OpenTofu install is tested"
  exit 1
fi
if [[ -e "${EWCCLI_HOME}/bin/tofu" ]]; then
  echo "::error::'${EWCCLI_HOME}/bin/tofu' already exists. Remove it, so that the EWCCLI-managed OpenTofu install is tested"
  exit 1
fi

# --- Step 3 ---
echo "Clone catalog repository (ref: '${CATALOG_REF}')"
PATH_TO_CATALOG_REPO="${GITHUB_WORKSPACE}/ewc-community-hub"
git clone \
  --depth 1 \
  --branch "${CATALOG_REF}" \
  "https://github.com/ewcloud/ewc-community-hub.git" \
  "${PATH_TO_CATALOG_REPO}"

# --- Step 4 ---
echo "Extract metadata of '${ITEM_NAME}' from catalog"
PATH_TO_CATALOG="${PATH_TO_CATALOG_REPO}/items.yaml"
item_metadata=$(yq '.spec.items."'"$ITEM_NAME"'" | del(.description)' $PATH_TO_CATALOG) # Drop the description attribute(for succinct step summary)

if [[ "${item_metadata}" == "null" ]]; then
  echo "::error::Item '${ITEM_NAME}' not found in catalog repository (ref: '${CATALOG_REF}')"
  exit 1
fi

# TODO: Re-write to use yq and item_metadata
PATH_TO_MAIN_FILE="$(jq -r '.values.pathToMainFile // "."' <<<"${item_json}")"

# TODO: Re-write to use yq
SENSITIVE_INPUTS="$(jq -c '[.values.inputSpec[]? | select(.sensitive == true) | .name]' <<<"${item_json}")"

# --- Step 5 ---
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
  #  --item-inputs x=1 --item-inputs y=["a","b"] --item-inputs z=null ...
  #  ```
  mapfile -t EXTRA_VARS < <(
    printf "%s" "${INPUT_SPEC_JSON}" | jq -r '
      to_entries[]
      | "--item-inputs"
      , (.key + "=" +
          if .value == null then
            (null | tojson)
          elif (.value | type) == "array" or (.value | type) == "object" then
            (.value | tojson)
          else
            (.value | tostring)
          end)
    '
  )
fi


# --- Step 6 ---
echo "Gather environment facts"
PYTHON_VERSION="$(python3 --version)"
EWCCLI_VERSION="$(ewc version 2>&1 || true)"

# --- Step 7 ---
echo "Create artifact directory"
ARTIFACTS_DIR="${GITHUB_WORKSPACE}/artifacts"
mkdir -p "$ARTIFACTS_DIR"

# --- Step 8 ---
echo "Setup SSH private and public keys (only needed for login)"
SSH_KEYS_DIR="${RUNNER_TEMP:-/tmp}/ewccli-e2e-ssh"
mkdir -p "${SSH_KEYS_DIR}"
chmod 700 "${SSH_KEYS_DIR}"
SSH_PRIVATE_KEY_FILE="${SSH_KEYS_DIR}/id_github_ewccli"
SSH_PUBLIC_KEY_FILE="${SSH_KEYS_DIR}/id_github_ewccli.pub"
printf "%s" "${SSH_PRIVATE_KEY}" >"${SSH_PRIVATE_KEY_FILE}"
printf "%s" "${SSH_PUBLIC_KEY}" >"${SSH_PUBLIC_KEY_FILE}"
chmod 600 "${SSH_PRIVATE_KEY_FILE}" "${SSH_PUBLIC_KEY_FILE}"

export EWC_CLI_SSH_PUBLIC_KEY_PATH="${SSH_PUBLIC_KEY_FILE}"
export EWC_CLI_SSH_PRIVATE_KEY_PATH="${SSH_PRIVATE_KEY_FILE}"

# --- Step 9 ---
declare -A STEP_RESULT=()
STEPS=(login dry-run dry-run-no-workspace deploy managed-runtime redeploy destroy no-resources-left)
declare -A STEP_DESCRIPTION=(
  [login]="\`ewc login\`"
  [dry-run]="\`ewc hub deploy --dry-run\` plans without changes"
  [dry-run-no-workspace]="Dry run of a new deployment leaves no workspace"
  [deploy]="\`ewc hub deploy\` creates the resources"
  [managed-runtime]="EWCCLI installed the managed OpenTofu runtime"
  [redeploy]="Re-running \`ewc hub deploy\` is a no-op"
  [destroy]="\`ewc hub destroy\` tears the deployment down"
  [no-resources-left]="No managed resources are left in state"
)
for step in "${STEPS[@]}"; do
  STEP_RESULT["${step}"]="skipped"
done

EWCCLI_HUB_CMD=(ewc hub --path-to-catalog "${PATH_TO_CATALOG}")
EWCCLI_LOGIN_CMD=(ewc login)
EWCCLI_DRY_RUN_CMD=("${EWCCLI_HUB_CMD[@]}" deploy "${ITEM_NAME}" --deployment-name "${DRY_RUN_DEPLOYMENT_NAME}" --dry-run "${ITEM_INPUT_ARGS[@]}")
EWCCLI_DEPLOY_CMD=("${EWCCLI_HUB_CMD[@]}" deploy "${ITEM_NAME}" --deployment-name "${DEPLOYMENT_NAME}" "${ITEM_INPUT_ARGS[@]}")
EWCCLI_DESTROY_CMD=("${EWCCLI_HUB_CMD[@]}" destroy "${ITEM_NAME}" --deployment-name "${DEPLOYMENT_NAME}")

echo "Login"
run_step login "${EWCCLI_LOGIN_CMD[@]}"

# NOTE: Remove local SSH keys, as Terraform Items should not need them
unset EWC_CLI_SSH_PUBLIC_KEY_PATH EWC_CLI_SSH_PRIVATE_KEY_PATH
rm -rf "${SSH_KEYS_DIR}"

if [[ "${STEP_RESULT[login]}" == "0" ]]; then
  # --- Step 10 ---
  echo "Dry run (plan only)"
  run_step dry-run "${EWCCLI_DRY_RUN_CMD[@]}"
  if dry_run_workspace="$(find_workspace "${DRY_RUN_DEPLOYMENT_NAME}")"; then
    echo "::error::Dry run left a workspace behind at '${dry_run_workspace}'"
    STEP_RESULT[dry-run-no-workspace]=1
  else
    STEP_RESULT[dry-run-no-workspace]=0
  fi

  # --- Step 11 ---
  echo "Deploy"
  run_step deploy "${EWCCLI_DEPLOY_CMD[@]}"

  if managed_runtime="$(find_managed_runtime)"; then
    echo "Managed OpenTofu runtime found at '${managed_runtime}'"
    STEP_RESULT[managed-runtime]=0
  else
    echo "::error::No managed OpenTofu runtime found under '${EWCCLI_HOME}/bin/tofu/'"
    STEP_RESULT[managed-runtime]=1
  fi

  # --- Step 12 ---
  if [[ "${STEP_RESULT[deploy]}" == "0" ]]; then
    echo "Re-deploy (idempotence check)"
    run_step redeploy "${EWCCLI_DEPLOY_CMD[@]}"
  fi

  # --- Step 13 ---
  echo "Cleanup"
  FALLBACK_CLEANUP_STATUS="not needed"
  deployment_workspace="$(find_workspace "${DEPLOYMENT_NAME}" || true)"
  if [[ "${STEP_RESULT[deploy]}" == "0" || -n "${deployment_workspace}" ]]; then
    run_step destroy "${EWCCLI_DESTROY_CMD[@]}"
    deployment_workspace="$(find_workspace "${DEPLOYMENT_NAME}" || true)"
    if [[ "${STEP_RESULT[destroy]}" == "0" ]]; then
      resources_left=0
      if [[ -n "${deployment_workspace}" ]]; then
        resources_left="$(count_managed_resources "${deployment_workspace}")"
      fi
      if [[ "${resources_left}" == "0" ]]; then
        STEP_RESULT[no-resources-left]=0
      else
        echo "::error::${resources_left} managed resource instance(s) left in state after destroy"
        STEP_RESULT[no-resources-left]=1
      fi
    fi
    if [[ "${STEP_RESULT[destroy]}" != "0" || "${STEP_RESULT[no-resources-left]}" != "0" ]] && [[ -n "${deployment_workspace}" ]]; then
      echo "::warning::Teardown via EWCCLI failed. Attempting fallback cleanup with the managed OpenTofu runtime"
      FALLBACK_CLEANUP_STATUS="failed"
      if fallback_cleanup "${deployment_workspace}"; then
        FALLBACK_CLEANUP_STATUS="succeeded"
      else
        echo "::error::Fallback cleanup failed. Resources of deployment '${DEPLOYMENT_NAME}' may be left in the tenancy"
      fi
    fi
  fi
else
  FALLBACK_CLEANUP_STATUS="not needed"
fi

EWCCLI_STATUS="passing"
for step in "${STEPS[@]}"; do
  if [[ "${STEP_RESULT[${step}]}" != "0" ]]; then
    EWCCLI_STATUS="failing"
  fi
done

MANAGED_RUNTIME="$(find_managed_runtime || echo "not installed")"
EWCCLI_VERSION_AFTER="$(ewc version 2>&1 || true)"

# --- Step 14 ---
echo "Collect artifacts"
pip freeze >"$ARTIFACTS_DIR/requirements.txt"

step_results_args=()
for step in "${STEPS[@]}"; do
  step_results_args+=(--arg "${step}" "${STEP_RESULT[${step}]}")
done
jq -n '$ARGS.named' "${step_results_args[@]}" >"$ARTIFACTS_DIR/ewccli_step_results.json"
printf "%s\n" "${item_metadata}" >"$ARTIFACTS_DIR/item_metadata.yaml"
jq . <<<"${masked_item_inputs}" >"$ARTIFACTS_DIR/item_inputs.json"
format_cmd "${EWCCLI_LOGIN_CMD[@]}" >"$ARTIFACTS_DIR/login.sh"
format_cmd "${EWCCLI_DRY_RUN_CMD[@]}" >"$ARTIFACTS_DIR/dry-run.sh"
format_cmd "${EWCCLI_DEPLOY_CMD[@]}" >"$ARTIFACTS_DIR/deploy.sh"
format_cmd "${EWCCLI_DESTROY_CMD[@]}" >"$ARTIFACTS_DIR/destroy.sh"

# --- Step 15 ---
echo "Write execution summary"
add_summary() {
  # NOTE: Helper for appending markdown
  printf "%s\n" "$1" >>"$GITHUB_STEP_SUMMARY"
}

add_code_block() {
  # NOTE: Helper for appending a file as a fenced code block
  add_summary "\`\`\`$1"
  cat "$2" >>"$GITHUB_STEP_SUMMARY"
  add_summary ""
  add_summary "\`\`\`"
  add_summary ""
}

add_summary "# EWC Community Hub EWCCLI - Terraform Deployment Test Summary"
add_summary ""
add_summary "- **Run ID:** \`${GITHUB_RUN_ID}\`"
add_summary "- **Repository:** \`${GITHUB_REPOSITORY:-unknown}\`"
add_summary "- **Branch/Tag:** \`${GITHUB_REF_NAME:-unknown}\`"
add_summary "- **Federee:** \`${EWC_CLI_LOGIN_FEDEREE}\`"
add_summary "- **Entrypoint:** \`ewc hub deploy ${ITEM_NAME} --deployment-name ${DEPLOYMENT_NAME}\`"
add_summary ""
add_summary "## Status"
add_summary "### Application Execution"
if [[ "${EWCCLI_STATUS}" == "passing" ]]; then
  add_summary "- **EWCCLI Status:** \`passing\` ${GREEN_LIGHT}"
else
  add_summary "- **EWCCLI Status:** \`failing\` ${RED_LIGHT}"
fi
add_summary "- **Fallback Cleanup:** \`${FALLBACK_CLEANUP_STATUS}\`"
add_summary ""
add_summary "| Step | Check | Result |"
add_summary "|------|-------|--------|"
for step in "${STEPS[@]}"; do
  result="${STEP_RESULT[${step}]}"
  if [[ "${result}" == "0" ]]; then
    light="${GREEN_LIGHT} \`exit 0\`"
  elif [[ "${result}" == "skipped" ]]; then
    light="${GRAY_LIGHT} \`skipped\`"
  else
    light="${RED_LIGHT} \`exit ${result}\`"
  fi
  add_summary "| \`${step}\` | ${STEP_DESCRIPTION[${step}]} | ${light} |"
done
add_summary ""
add_summary "## Environment Details"
add_summary "### Prerequisites"
add_summary "- \`${PYTHON_VERSION}\`"
add_summary "- EWCCLI before deployment: \`$(head -n 1 <<<"${EWCCLI_VERSION}")\`"
add_summary "- EWCCLI after deployment:"
add_summary "\`\`\`txt"
add_summary "${EWCCLI_VERSION_AFTER}"
add_summary "\`\`\`"
add_summary "- Managed OpenTofu runtime: \`${MANAGED_RUNTIME}\`"
add_summary "### Item"
add_code_block yaml "$ARTIFACTS_DIR/item_metadata.yaml"
add_summary "### Item Inputs"
add_code_block json "$ARTIFACTS_DIR/item_inputs.json"
add_summary "### Execution Plan"
add_code_block bash "$ARTIFACTS_DIR/login.sh"
add_code_block bash "$ARTIFACTS_DIR/dry-run.sh"
add_code_block bash "$ARTIFACTS_DIR/deploy.sh"
add_code_block bash "$ARTIFACTS_DIR/destroy.sh"
add_summary "---"
add_summary "_Summary Auto-generated by \"EWCCLI Test Deploy\" GitHub Action_"

cp $GITHUB_STEP_SUMMARY "$ARTIFACTS_DIR/summary.md"

# --- Step 16 ---
echo "Re-raising test errors (if any)"
if [[ "${EWCCLI_STATUS}" == "failing" ]]; then
  echo "::error::Deployment test(s) FAILING!. See the Summary or logs for details"
  exit 1
fi
