# Copyright (c) 2017 Platform9 Systems Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either expressed or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import uuid

from googleapiclient.discovery import build
from oauth2client.client import GoogleCredentials
from oslo_log import log as logging

from neutron_lib import exceptions as e
from neutron._i18n import _LI, _
from oslo_service import loopingcall
from six.moves import urllib

LOG = logging.getLogger(__name__)


class GceOperationError(Exception):
    pass


class GceResourceNotFound(e.NotFound):
    message = _("GCE Resource %(name)s %(identifier)s was not found")


def list_instances(compute, project, zone):
    """Returns list of GCE instance resources for specified project
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param zone: string, GCE Name of zone
    :return: Instances information
    :rtype: list
    """
    result = compute.instances().list(project=project, zone=zone).execute()
    if 'items' not in result:
        return []
    return result['items']


def get_instance(compute, project, zone, instance):
    """Get GCE instance information
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param zone: string, GCE Name of zone
    :param instance: string, Name of the GCE instance resource
    :return: Instance information
    :rtype: dict
    """
    result = compute.instances().get(project=project, zone=zone,
                                     instance=instance).execute()
    return result


def wait_for_operation(compute, project, operation, interval=1, timeout=60):
    """Wait for GCE operation to complete, raise error if operation failure
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param zone: string, GCE Name of zone
    :param operation: object, Operation resource obtained by calling GCE API
    :param interval: int, Time period(seconds) between two GCE operation checks
    :param timeout: int, Absoulte time period(seconds) to monitor GCE operation
    """

    def watch_operation(name, request):
        result = request.execute()
        if result['status'] == 'DONE':
            LOG.info(
                _LI("Operation %s status is %s") % (name, result['status']))
            if 'error' in result:
                raise GceOperationError(result['error'])
            raise loopingcall.LoopingCallDone()

    operation_name = operation['name']

    if 'zone' in operation:
        zone = operation['zone'].split('/')[-1]
        monitor_request = compute.zoneOperations().get(
            project=project, zone=zone, operation=operation_name)
    elif 'region' in operation:
        region = operation['region'].split('/')[-1]
        monitor_request = compute.regionOperations().get(
            project=project, region=region, operation=operation_name)
    else:
        monitor_request = compute.globalOperations().get(
            project=project, operation=operation_name)

    timer = loopingcall.FixedIntervalWithTimeoutLoopingCall(
        watch_operation, operation_name, monitor_request)
    timer.start(interval=interval, timeout=timeout).wait()


def get_gce_service(service_key):
    """Returns GCE compute resource object for interacting with GCE API
    :param service_key: string, Path of service key obtained from
        https://console.cloud.google.com/apis/credentials
    :return: :class:`Resource <Resource>` object
    :rtype: googleapiclient.discovery.Resource
    """
    credentials = GoogleCredentials.from_stream(service_key)
    service = build('compute', 'v1', credentials=credentials)
    return service


def create_network(compute, project, name):
    """Create network in GCE
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param name: string, GCE Name of network
    :return: Operation information
    :rtype: dict
    """
    body = {'autoCreateSubnetworks': False, 'name': name}
    return compute.networks().insert(project=project, body=body).execute()


def get_network(compute, project, name):
    """Get info of network in GCE
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param name: string, GCE Name of network
    :return: GCE Network information
    :rtype: dict
    """
    result = compute.networks().get(project=project, network=name).execute()
    return result


def create_subnet(compute, project, region, name, ipcidr, network_link):
    """Create subnet with particular GCE network
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :param name: string, Subnet name
    :param ipcidr: string, IP CIDR for subnet
    :param network_link: url, GCE network resource url
    :return: Operation information
    :rtype: dict
    """
    body = {
        'privateIpGoogleAccess': False,
        'name': name,
        'ipCidrRange': ipcidr,
        'network': network_link
    }
    return compute.subnetworks().insert(project=project, region=region,
                                        body=body).execute()


def delete_subnet(compute, project, region, name):
    """Delete subnet in GCE
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :param name: string, Subnet name
    :return: Operation information
    :rtype: dict
    """
    return compute.subnetworks().delete(project=project, region=region,
                                        subnetwork=name).execute()


def delete_network(compute, project, name):
    """Delete network in GCE
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param name: string, GCE network name
    :return: Operation information
    :rtype: dict
    """
    return compute.networks().delete(project=project, network=name).execute()


def create_static_ip(compute, project, region, name):
    """Create global static IP
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :param name: string, Static IP name
    :return: Operation information
    :rtype: dict
    """
    return compute.addresses().insert(project=project, region=region, body={
        'name': name,
    }).execute()


def get_static_ip(compute, project, region, name):
    """Get static IP
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :param name: string, Static IP name
    :return: GCE static IP information
    :rtype: dict
    """
    return compute.addresses().get(project=project, region=region,
                                   address=name).execute()


def delete_static_ip(compute, project, region, name):
    """Delete static IP
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :param name: string, Static IP name
    :return: Operation information
    :rtype: dict
    """
    return compute.addresses().delete(project=project, region=region,
                                      address=name).execute()


def get_floatingip(compute, project, region, ip):
    """Get details of static IP in GCE
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :param ip: string, GCE Static IP
    :return: GCE address information
    :rtype: dict
    """
    query = 'address eq %s' % ip
    result = compute.addresses().list(project=project, region=region,
                                      filter=query).execute()
    if 'items' in result and len(result['items']) == 1:
        return result['items'][0]

    raise GceResourceNotFound(name='Floating IP', identifier=ip)


def allocate_floatingip(compute, project, region):
    """Get global static IP in GCE
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :return: GCE static IP
    :rtype: str
    """
    name = 'ip-' + str(uuid.uuid4())
    operation = create_static_ip(compute, project, region, name)
    wait_for_operation(compute, project, operation)
    address = get_static_ip(compute, project, region, name)
    return address['address']


def delete_floatingip(compute, project, region, ip):
    """Delete particular static IP
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param region: string, GCE region
    :param ip: string, GCE Static IP
    """
    address = get_floatingip(compute, project, region, ip)
    name = address['name']
    operation = delete_static_ip(compute, project, region, name)
    wait_for_operation(compute, project, operation)


def assign_floatingip(compute, project, zone, fixedip, floatingip):
    """Assign static IP to interface with mentioned fixed IP
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param zone: string, GCE zone
    :param fixedip: string, GCE private IP from private network
    :param floatingip: string, GCE static IP
    """
    instances = list_instances(compute, project, zone)
    instance_name = None
    for instance in instances:
        for interface in instance['networkInterfaces']:
            if interface['networkIP'] == fixedip:
                instance_name = instance['name']
                interface_name = interface['name']
                break
    if not instance_name:
        raise GceResourceNotFound(name='Instance with fixed IP',
                                  identifier=fixedip)

    LOG.info(
        _LI('Assigning floating ip %s to instance %s') % (floatingip,
                                                          instance_name))

    operation = compute.instances().addAccessConfig(
        project=project, zone=zone, instance=instance_name,
        networkInterface=interface_name, body={
            'type': 'ONE_TO_ONE_NAT',
            'name': 'External NAT',
            'natIP': floatingip
        }).execute()
    wait_for_operation(compute, project, operation)


def release_floatingip(compute, project, zone, floatingip):
    """Release GCE static IP from instances using it
    :param compute: GCE compute resource object using googleapiclient.discovery
    :param project: string, GCE Project Id
    :param zone: string, GCE zone
    :param floatingip: string, GCE static IP
    """
    address = get_floatingip(compute, project, zone, floatingip)
    for user in address.get('users', []):
        # Parse instance info
        # Eg. /compute/v1/projects/<name>/zones/<zone>/instances/<name>

        items = urllib.parse.urlparse(user).path.strip('/').split('/')
        if len(items) < 4 or items[-2] != 'instances':
            LOG.warning(
                _LI('Unknown referrer %s to GCE static IP %s') % (user,
                                                                  floatingip))
            continue

        instance, zone = items[-1], items[-3]
        instance_info = get_instance(compute, project, zone, instance)
        for interface in instance_info['networkInterfaces']:
            for accessconfig in interface.get('accessConfigs', []):
                if accessconfig.get('natIP') == floatingip:
                    LOG.info(
                        _LI('Releasing %s from instance %s') % (floatingip,
                                                                instance))
                    operation = compute.instances().deleteAccessConfig(
                        project=project, zone=zone, instance=instance,
                        accessConfig=accessconfig['name'],
                        networkInterface=interface['name']).execute()
                    wait_for_operation(compute, project, operation)
