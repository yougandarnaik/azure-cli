# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
import time
import uuid

from azure.cli.core.prompting import prompt_pass, NoTTYException
from azure.mgmt.datalake.analytics.account.models import (DataLakeAnalyticsAccountUpdateParameters,
                                                          FirewallRule,
                                                          DataLakeAnalyticsAccount,
                                                          DataLakeStoreAccountInfo)

from azure.mgmt.datalake.analytics.job.models import (JobType,
                                                      JobState,
                                                      JobInformation,
                                                      USqlJobProperties)
# pylint: disable=line-too-long
from azure.mgmt.datalake.analytics.catalog.models import (DataLakeAnalyticsCatalogCredentialCreateParameters,
                                                          DataLakeAnalyticsCatalogCredentialUpdateParameters)
from azure.cli.core.commands.client_factory import get_mgmt_service_client
from azure.cli.core._util import CLIError
import azure.cli.core.azlogging as azlogging

logger = azlogging.get_az_logger(__name__)
# account customiaztions
def list_adla_account(client, resource_group_name=None):
    account_list = client.list_by_resource_group(resource_group_name=resource_group_name) \
        if resource_group_name else client.list()
    return list(account_list)

# pylint: disable=too-many-arguments
def create_adla_account(client,
                        resource_group_name,
                        account_name,
                        default_datalake_store,
                        location=None,
                        tags=None,
                        max_degree_of_parallelism=30,
                        max_job_count=3,
                        query_store_retention=30,
                        tier=None):
    adls_list = list()
    adls_list.append(DataLakeStoreAccountInfo(default_datalake_store))
    location = location or _get_resource_group_location(resource_group_name)
    create_params = DataLakeAnalyticsAccount(location,
                                             default_datalake_store,
                                             adls_list,
                                             tags=tags,
                                             max_degree_of_parallelism=max_degree_of_parallelism,
                                             max_job_count=max_job_count,
                                             query_store_retention=query_store_retention,
                                             new_tier=tier)

    return client.create(resource_group_name, account_name, create_params)

# pylint: disable=too-many-arguments
def update_adla_account(client,
                        account_name,
                        resource_group_name,
                        tags=None,
                        max_degree_of_parallelism=None,
                        max_job_count=None,
                        query_store_retention=None,
                        tier=None,
                        firewall_state=None,
                        allow_azure_ips=None):
    update_params = DataLakeAnalyticsAccountUpdateParameters(
        tags=tags,
        max_degree_of_parallelism=max_degree_of_parallelism,
        max_job_count=max_job_count,
        query_store_retention=query_store_retention,
        new_tier=tier,
        firewall_state=firewall_state,
        firewall_allow_azure_ips=allow_azure_ips)

    return client.update(resource_group_name, account_name, update_params)

# firewall customizations
# pylint: disable=too-many-arguments
def add_adla_firewall_rule(client,
                           account_name,
                           firewall_rule_name,
                           start_ip_address,
                           end_ip_address,
                           resource_group_name):
    create_params = FirewallRule(start_ip_address, end_ip_address)
    return client.create_or_update(resource_group_name,
                                   account_name,
                                   firewall_rule_name,
                                   create_params)

# catalog customizations
# pylint: disable=too-many-arguments
def create_adla_catalog_credential(client,
                                   account_name,
                                   database_name,
                                   credential_name,
                                   credential_user_name,
                                   uri,
                                   credential_user_password=None):

    if not credential_user_password:
        try:
            credential_user_password = prompt_pass('Password:', confirm=True)
        except NoTTYException:
            # pylint: disable=line-too-long
            raise CLIError('Please specify both --user-name and --password in non-interactive mode.')

    create_params = DataLakeAnalyticsCatalogCredentialCreateParameters(credential_user_password,
                                                                       uri,
                                                                       credential_user_name)
    client.create_credential(account_name, database_name, credential_name, create_params)

# pylint: disable=too-many-arguments
def update_adla_catalog_credential(client,
                                   account_name,
                                   database_name,
                                   credential_name,
                                   credential_user_name,
                                   uri,
                                   credential_user_password=None,
                                   new_credential_user_password=None):
    if not credential_user_password:
        try:
            credential_user_password = prompt_pass('Current Password:', confirm=True)
        except NoTTYException:
            # pylint: disable=line-too-long
            raise CLIError('Please specify --user-name --password and --new-password in non-interactive mode.')

    if not new_credential_user_password:
        try:
            new_credential_user_password = prompt_pass('New Password:', confirm=True)
        except NoTTYException:
            # pylint: disable=line-too-long
            raise CLIError('Please specify --user-name --password and --new-password in non-interactive mode.')

    update_params = DataLakeAnalyticsCatalogCredentialUpdateParameters(credential_user_password,
                                                                       new_credential_user_password,
                                                                       uri,
                                                                       credential_user_name)
    client.update_credential(account_name, database_name, credential_name, update_params)

# job customizations
# pylint: disable=too-many-arguments
def submit_adla_job(client,
                    account_name,
                    job_name,
                    script,
                    runtime_version=None,
                    compile_mode=None,
                    compile_only=False,
                    degree_of_parallelism=1,
                    priority=1000):
    if not script:
        # pylint: disable=line-too-long
        raise CLIError('Could not read script content from the supplied --script param. It is either empty or an invalid file. value: {}'.format(script))

    job_properties = USqlJobProperties(script)
    if runtime_version:
        job_properties.runtime_version = runtime_version

    if compile_mode:
        job_properties.compile_mode = compile_mode

    submit_params = JobInformation(job_name,
                                   JobType.usql,
                                   job_properties,
                                   degree_of_parallelism,
                                   priority)
    if compile_only:
        return client.build(account_name, submit_params)

    job_id = _get_uuid_str()

    return client.create(account_name, job_id, submit_params)

# pylint: disable=superfluous-parens
def wait_adla_job(client,
                  account_name,
                  job_id,
                  wait_interval_sec=5,
                  max_wait_time_sec=-1):
    if wait_interval_sec < 1:
        # pylint: disable=line-too-long
        raise CLIError('wait times must be greater than 0 when polling jobs. Value specified: {}'.format(wait_interval_sec))

    job = client.get(account_name, job_id)
    time_waited_sec = 0
    while job.state != JobState.ended:
        if max_wait_time_sec > 0 and time_waited_sec >= max_wait_time_sec:
            # pylint: disable=line-too-long
            raise CLIError('Data Lake Analytics Job with ID: {0} has not completed in {1} seconds. Check job runtime or increase the value of --max-wait-time-sec'.format(job_id, time_waited_sec))
        logger.info('Job is not yet done. Current job state: \'%s\'', job.state)
        time.sleep(wait_interval_sec)
        job = client.get(account_name, job_id)

    return job

# helpers
def _get_uuid_str():
    return str(uuid.uuid1())

def _get_resource_group_location(resource_group_name):
    from azure.mgmt.resource.resources import ResourceManagementClient
    client = get_mgmt_service_client(ResourceManagementClient)
    # pylint: disable=no-member
    return client.resource_groups.get(resource_group_name).location
