#!/usr/bin/env python
#
# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details


"""Kubernetes backend driver."""

import sys
import json
from typing import List, Dict, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.config.config_exception import ConfigException
from ewccli.logger import get_logger
from ewccli.backends.kubernetes.exceptions import ResourceAlreadyExistsError


_LOGGER = get_logger(__name__)


class KubernetesBackend:
    """Kubernetes backend class."""


    def __init__(
        self,
        token: Optional[str] = None,
        host: Optional[str] = None,
        verify_ssl: bool = True
    ):
        """
        Initialize Kubernetes client using token or kubeconfig.

        :param token: Optional Bearer token for auth.
        :param host: Optional Kubernetes API server URL (used with token).
        :param verify_ssl: Whether to verify SSL certificates.
        """
        if token and host:
            try:
                configuration = client.Configuration()
                configuration.host = host
                configuration.verify_ssl = verify_ssl
                configuration.api_key = {"authorization": f"Bearer {token}"}
                client.Configuration.set_default(configuration)
                _LOGGER.debug("Initialized Kubernetes client with token and host.")
            except Exception as e:
                _LOGGER.error(f"❌ Failed to initialize Kubernetes client with token+host: {e}")
                sys.exit(1)
        else:
            try:
                config.load_kube_config()
                _LOGGER.debug("Loaded kubeconfig from local file.")
            except ConfigException:
                _LOGGER.error(
                    "❌ Failed to load Kubernetes configuration.\n"
                    "Primary option: run `ewc login` to generate configuration.\n"
                    "Alternative options:\n"
                    "  - Ensure your KUBECONFIG environment variable points to a valid kubeconfig file.\n"
                    "  - Ensure ~/.kube/config exists and is valid."
                )
                sys.exit(1)

        self.custom_api = client.CustomObjectsApi()
        self.core_api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
        self.api = client.ApiextensionsV1Api()


    def delete_custom_resource(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str
    ) -> dict:
        """
        Delete a custom resource by name.

        :param group: The API group of the CRD (e.g., 'dns.europeanweather.cloud').
        :param version: The API version (e.g., 'v1alpha1').
        :param namespace: The namespace of the resource.
        :param plural: The plural name of the CRD (e.g., 'records').
        :param name: The name of the custom resource.
        :return: API response dict.
        """
        try:
            return self.custom_api.delete_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name
            )
        except ApiException as e:
            if e.status == 404:
                _LOGGER.error(
                    f"[404] Resource not found: group={group}, version={version}, "
                    f"namespace={namespace}, plural={plural}"
                )
                return {}
            elif e.status == 403:
                _LOGGER.error(
                    f"[403] Forbidden: insufficient permissions to list "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return {}
            elif e.status == 401:
                _LOGGER.error(
                    f"[401] Unauthorized: authentication failed while accessing "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return {}
            else:
                raise Exception(
                    f"Kubernetes API error [{e.status}]: {e.reason}\nResponse: {e.body}"
                )


    def describe_custom_resource(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        name: str
    ) -> dict:
        """
        Retrieve a specific custom resource by name.

        :param group: The API group of the CRD (e.g., 'dns.europeanweather.cloud').
        :param version: The API version (e.g., 'v1alpha1').
        :param namespace: The namespace of the resource.
        :param plural: The plural name of the resource (e.g., 'records').
        :param name: The name of the resource.
        :return: The resource as a dict.
        """
        try:
            return self.custom_api.get_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                name=name
            )
        except ApiException as e:
            if e.status == 404:
                _LOGGER.error(
                    f"[404] Resource not found: group={group}, version={version}, "
                    f"namespace={namespace}, plural={plural}"
                )
                return {}
            elif e.status == 403:
                _LOGGER.error(
                    f"[403] Forbidden: insufficient permissions to list "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return {}
            elif e.status == 401:
                _LOGGER.error(
                    f"[401] Unauthorized: authentication failed while accessing "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return {}
            else:
                raise Exception(
                    f"Kubernetes API error [{e.status}]: {e.reason}\nResponse: {e.body}"
                )


    def list_custom_resources(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str
    ) -> list:
        """List all custom resources of a type."""
        try:
            return self.custom_api.list_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural
            )["items"]
        except ApiException as e:
            if e.status == 404:
                _LOGGER.error(
                    f"[404] Resource not found: group={group}, version={version}, "
                    f"namespace={namespace}, plural={plural}"
                )
                return []
            elif e.status == 403:
                _LOGGER.error(
                    f"[403] Forbidden: insufficient permissions to list "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return []
            elif e.status == 401:
                _LOGGER.error(
                    f"[401] Unauthorized: authentication failed while accessing "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return []
            else:
                raise Exception(
                    f"Kubernetes API error [{e.status}]: {e.reason}\nResponse: {e.body}"
                )


    def create_custom_resource(
        self,
        group: str,
        version: str,
        namespace: str,
        plural: str,
        body: dict,
    ) -> dict:
        """
        Create a custom resource in the given namespace.

        :param group: The API group of the CRD (e.g., 'dns.europeanweather.cloud').
        :param version: The API version (e.g., 'v1alpha1').
        :param namespace: The Kubernetes namespace to create the resource in.
        :param plural: The plural name of the CRD (e.g., 'records').
        :param body: A dictionary representing the custom resource object (the full CR body).
        :return: The created custom resource as a dict.
        """
        try:
            return self.custom_api.create_namespaced_custom_object(
                group=group,
                version=version,
                namespace=namespace,
                plural=plural,
                body=body,
            )
        except ApiException as e:
            err_body = json.loads(e.body)
            # handle AlreadyExists (409) similarly to Validation (422)
            if err_body.get("code") == 409 or err_body.get("reason") == "AlreadyExists":
                resource_name = body.get("metadata", {}).get("name", "<unknown>")
                _LOGGER.error(
                    f"⚠️ Resource '{resource_name}' already exists in namespace '{namespace}'. Skipping creation."
                )
            elif err_body.get("code") == 422:
                # Parse and format Kubernetes validation errors
                try:
                    err_body = json.loads(e.body)
                    _LOGGER.error("❌ Validation failed:")
                    _LOGGER.error(f"Message: {err_body.get('message')}")
                    causes = err_body.get("details", {}).get("causes", [])
                    for cause in causes:
                        field = cause.get("field", "unknown field")
                        reason = cause.get("reason", "unknown reason")
                        msg = cause.get("message", "")
                        _LOGGER.error(f" - {field}: {reason} – {msg}")
                except Exception:
                    _LOGGER.error("❌ Error parsing validation response.")
                    _LOGGER.error(e.body)
            elif e.status == 404:
                _LOGGER.error(
                    f"[404] Resource not found: group={group}, version={version}, "
                    f"namespace={namespace}, plural={plural}"
                )
                return {}
            elif e.status == 403:
                _LOGGER.error(
                    f"[403] Forbidden: insufficient permissions to list "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return {}
            elif e.status == 401:
                _LOGGER.error(
                    f"[401] Unauthorized: authentication failed while accessing "
                    f"{plural}.{group} in namespace '{namespace}'.\n"
                    f"Details: {e.body}"
                )
                return {}
            else:
                # Generic API error -> compact output
                _LOGGER.error(
                    f"[{e.status}] Kubernetes API error: {e.reason}\n{e.body}",
                )
                raise Exception("Kubernetes API request failed")


    def list_pods(
        self,
        namespace: str,
    ) -> list:
        """List pods in namespace.
        
            pods = list_pods(namespace="default")
            for pod in pods.items:
                print(pod.metadata.name)
        """
        return self.core_api.list_namespaced_pod(namespace=namespace)


    def list_custom_resource_definitions(
        self,
    ) -> List[Dict[str, str]]:
        """
        List all Custom Resource Definitions (CRDs) in the cluster.

        :return: List of dicts with keys: kind, group, version, plural

        crds = list_custom_resource_definitions()
        for crd in crds:
            print(f"{crd['kind']} - {crd['group']}/{crd['version']} (plural: {crd['plural']})")
        """
        crds = self.api.list_custom_resource_definition()
        result = []

        for crd in crds.items:
            kind = crd.spec.names.kind
            group = crd.spec.group
            plural = crd.spec.names.plural

            # Get first served version (or fallback to first version)
            version = next((v.name for v in crd.spec.versions if v.served), crd.spec.versions[0].name)

            result.append({
                "kind": kind,
                "group": group,
                "version": version,
                "plural": plural
            })

        return result
