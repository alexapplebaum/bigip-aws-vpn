#!/usr/bin/python
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = """
---
module: ec2_vpn_gateway
description:
  - Returns information about the vpn gateway.
  - Will be marked changed when called only if state is changed.
short_description: Creates or destroys a vpn gateway and attaches to a vpc.
version_added: "X.X"
author: Alex Applebaum
options:
  state:
    description:
      - if state is passed, create or destroy the vpn gateway
    required: true
  id:
    description:
      - ID of vpn gateway. Will list information about that gateway or delete is state is passed. 
    required: false
    default: None
    version_added: "X.X"
  tags: 
      description:
      - Tags for vpn gateway object. Need to at least do a name. ex. { "Name" : "Example VPC Gateway" }
    required: true
    default: None
    version_added: "X.X"
  type: 
    description: 
      - type of ipsec. Currently there is only one by default "ipsec.1"
    default: ipsec.1
    required: false
  vpc:
      description: 
      - Virtual Private Cloud ID to attach the gateway to.
    default: None
    required: false
  availability_zone:
      description: 
      - Availability Zone
    default: None
    required: false
  region:
    description:
      - The AWS region to use. If not specified then the value of the EC2_REGION environment variable, if any, is used.
    required: false
    aliases: ['aws_region', 'ec2_region']


  

extends_documentation_fragment: aws
"""

EXAMPLES = """
# Note: None of these examples set aws_access_key, aws_secret_key, or region.
# It is assumed that their matching environment variables are set.
# structure based on ec2_elb_lb module

# Basic provisioning example
- local_action:
    module: ec2_vpn_gateway
    state: present
    availability_zone: us-west-2a
    vpc: vpc-fgafegf
    region: us-west-2
    tags: { "Name": "example_vpn_gateway" }


# Ensure vpn_gateway is deleted by ID (Recommended)
- local_action:
    module: ec2_vpn_gateway
    id: vgw-e961bef7
    vpc: vpc-fgafegf
    state: absent
    region: us-west-2
    tags: { "Name": "example_vpn_gateway" }

# Try to delete vpn_gateway by Tag (Depends on Unique Keys)
- local_action:
    module: ec2_vpn_gateway
    vpc: vpc-fgafegf
    state: absent
    region: us-west-2
    tags: { "Name": "example_vpn_gateway" }

"""

import sys
import os


try:
    import boto
    import boto.vpc
    import boto.vpc.vpngateway
    from boto.regioninfo import RegionInfo
except ImportError:
    print "failed=True msg='boto required for this module'"
    sys.exit(1)


class VPNGatewayManager(object):
    """Handles VPC Gateway creation and destruction"""

    def __init__(self, module, id=None, type=None, availability_zone=None, vpc=None, route_table_ids=None, tags=None, region=None, **aws_connect_params ):

        self.module = module
        self.id = id
        self.type = type
        self.availability_zone = availability_zone
        self.vpc = vpc
        self.route_table_ids = route_table_ids
        self.tags = tags


        self.region = region
        self.aws_connect_params = aws_connect_params

        self.changed = False
        self.status = 'gone'
        self.attach_status = 'detached'
        self.aws_conn = self._get_aws_connection()
        self.vpn_gw = self._get_vpn_gateway()

    def ensure_ok(self):
        """Create the vpngateway"""
        if not self.vpn_gw:
            self._create_vpn_gw()
            #self._set_tags()
        
        #Update tags no matter what (need to make declaritive though, 
        # i.e. clean up / delete ones not in list so only tags remaining are ones explicity passed     
        self._set_tags()

        if self.vpc and self.id:
            self._attach_vpn_gw()

    def ensure_gone(self):
        """Destroy the VPN Gateway"""
        if self.vpc and self.id:
            self._detach_vpn_gw()

        if self.vpn_gw:
            #self.module.fail_json(msg="self.vpn_gw true: Attempting to delete vpngateway")
            self._delete_vpn_gw()


    def get_info(self):
        try:
            check_aws = self.aws_conn.get_all_vpn_gateways( vpn_gateway_ids = [ self.id ] )[0]
        except:
            check_aws = None

        if not check_aws:
            info = {
                'id': self.id,
                'status': self.status
            }
        else:
            info = {
                'id': check_aws.id,
                'availability_zone': check_aws.availability_zone,
                'type': check_aws.type,
                'status': self.status,
                'attach_status': self.attach_status
            }

        return info

    def _get_vpn_gateway(self):

        #self.module.fail_json(msg="aws_conn: " + str(self.aws_conn) )

        vpn_gws = self.aws_conn.get_all_vpn_gateways()
        found_vpn_gws = []

        # search by id
        if self.id:
            for vpn_gw in vpn_gws:
                #self.module.fail_json(msg="vpn_gw_id: " + str(vpn_gw.id) )
                if self.id == vpn_gw.id:
                    self.status = 'ok'
                    return vpn_gw

        # Else search for tags
        elif self.tags:
            for vpn_gw in vpn_gws:
                    # Get all tags for each of the found VPCs
                    vpn_gw_tags = dict((t.name, t.value) for t in self.aws_conn.get_all_tags(filters={'resource-id': vpn_gw.id}))

                    # If the supplied list of ID Tags match a subset of the VPN Tags, we found our VPN
                    if self.tags and set(self.tags.items()).issubset(set(vpn_gw_tags.items())):
                        found_vpn_gws.append(vpn_gw)

            #vpn_gw = None

            if len(found_vpn_gws) == 1:
                vpn_gw = found_vpn_gws[0]
                self.id = vpn_gw.id
                self.status = 'ok'
                return vpn_gw

            if len(found_vpn_gws) > 1:
                self.module.fail_json(msg='Found more than one vpn gateway based on the supplied criteria, aborting')

            #self.module.fail_json(msg="vpn_gws: " + str(vpn_gws) )

    def _create_vpn_gw(self):

        self.vpn_gw = self.aws_conn.create_vpn_gateway( type=self.type, 
                                                        availability_zone=self.availability_zone )
        if self.vpn_gw:
            self.changed = True
            self.status = 'created'
            self.id=self.vpn_gw.id


    def _delete_vpn_gw(self):
        # True if succeeds, exception raised if not
        result = self.aws_conn.delete_vpn_gateway(self.id)
        if result:
            self.changed = True
            self.status = 'deleted'

    def _attach_vpn_gw(self):
        # True if succeeds, exception raised if not
        result = self.aws_conn.attach_vpn_gateway( self.id, self.vpc )
        if result:
            self.changed = True
            self.attach_status = 'attached'

    def _detach_vpn_gw(self):
        # True if succeeds, exception raised if not
        result = self.aws_conn.detach_vpn_gateway( self.id, self.vpc )
        if result:
            self.changed = True
            self.attach_status = 'detached'

    def _enable_route_propagation(self):
        # True if succeeds, exception raised if not
        results = []
        for route in self.route_table_ids:
            result = self.aws_conn.enable_vgw_route_propagation(route, self.id )
            if result: 
                results.append(result)

        if results:
            self.changed = True

    def _disable_route_propagation(self):
        # True if succeeds, exception raised if not
        results = []
        for route in self.route_table_ids:
            result = self.aws_conn.disable_vgw_route_propagation(route, self.id )
            if result: 
                results.append(result)

        if results:
            self.changed = True

    def _set_tags(self):
        resource = self.id
        filters = { 'resource-id' : resource }
        gettags = self.aws_conn.get_all_tags(filters=filters)

        dictadd = {}
        dictremove = {}
        baddict = {}
        tagdict = {}

        for tag in gettags:
            tagdict[tag.name] = tag.value

        # if set(self.tags.items()).issubset(set(tagdict.items())):
        #         module.exit_json(msg="Tags already exists in %s." %resource, changed=False)
        # else:
        for (key, value) in set(self.tags.items()):
            if (key, value) not in set(tagdict.items()):
                    dictadd[key] = value
        if dictadd:
            tagger = self.aws_conn.create_tags(resource, dictadd)

        gettags = self.aws_conn.get_all_tags(filters=filters)

        #self.module.fail_json(msg="gettags: " + str(gettags) + " resource: " + resource )       

    def _get_aws_connection(self):
        try:
            return connect_to_aws(boto.vpc, self.region,
                                  **self.aws_connect_params)
        except boto.exception.NoAuthHandlerFound, e:
            self.module.fail_json(msg=str(e))


def main():
    argument_spec = ec2_argument_spec()
    argument_spec.update(dict(
            state={ 'required': True, 'choices': ['present', 'absent'] },
            id={ 'default': None, 'required': False, 'type': 'str' },
            type={ 'default': 'ipsec.1', 'required': False, 'type': 'str' },
            availability_zone={ 'default': None, 'required': False, 'type': 'str' },
            vpc={ 'default': None, 'required': False, 'type': 'str'},
            route_table_ids={ 'default': None, 'required': False, 'type': 'list' },
            tags={ 'required': True, 'type': 'dict' }
        )
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
    )


    region, ec2_url, aws_connect_params = get_aws_connection_info(module)


    state = module.params['state']
    id = module.params['id']
    type = module.params['type']
    availability_zone = module.params['availability_zone']
    vpc = module.params['vpc']
    route_table_ids = module.params['route_table_ids']
    tags = module.params['tags']


    if not region:
        module.fail_json(msg="Region must be specified as a parameter, in EC2_REGION or AWS_REGION environment variables or in boto configuration file")


    vpn_gw_man = VPNGatewayManager( module, id, type, availability_zone, vpc, route_table_ids, tags,
                                    region, **aws_connect_params )
 
    if state == 'present':
        if route_table_ids and vpn_gw_man.vpn_gw:
            vpn_gw_man._enable_route_propagation()
        else: 
            vpn_gw_man.ensure_ok()

    if state == 'absent':
        if route_table_ids and vpn_gw_man.vpn_gw:
            vpn_gw_man._disable_route_propagation()
        else: 
            vpn_gw_man.ensure_gone()


    ansible_facts = {'ec2_vpn_gateway': 'info'}
    ec2_facts_result = dict(changed=vpn_gw_man.changed,
                            vpn_gw=vpn_gw_man.get_info(),
                            ansible_facts=ansible_facts)

    module.exit_json(**ec2_facts_result)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

main()
