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
module: ec2_vpn_connection
description:
  - Returns information about the vpn connection.
  - Will be marked changed when called only if state is changed.
short_description: Creates or destroys a vpn connection 
version_added: "X.X"
author: Alex Applebaum
options:
  state:
    description:
      - if state is passed, create or destroy the vpn connection
    required: true
  id:
    description:
      - ID of vpn connection. Will list information about that connection or delete if state is passed. 
    required: false
    default: None
    version_added: "X.X"
  tags: 
      description:
      - Tags for vpn connection object. Need to at least do a name. ex. { "Name" : "Example VPN connection" }
    required: true
    default: None
    version_added: "X.X"
  type: 
    description: 
      - type of ipsec. Currently there is only one by default "ipsec.1"
    default: ipsec.1
    required: false
  cgw:
      description: 
      - Customer Gateway ID to associate VPN Connection.
    default: None
    required: false
  vpn_gw:
      description: 
      - VPN Gateway ID to associate VPN Connection.
    default: None
    required: false
  vpc:
      description: 
      - Virtual Private Cloud ID to attach the connection to.
    default: None
    required: false
  static_routes_only:
      description: 
      - Static Routes Only Flag (bool)
    default: false
    required: false
  static_routes:
      description: 
      - List of Destination Static Routes (CIDR). ex. [10.1.1.0/24, 10.1.2.0/24]
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
    module: ec2_vpn_connection
    state: present
    cgw: cgw-efgi31g
    vpn_gw: vgw-e961bef7
    vpc: vpc-fgafegf
    region: us-west-2
    tags: { "Name": "example_vpn_connection" }


# Ensure vpn_connection is deleted by ID (Recommended)
- local_action:
    module: ec2_vpn_connection
    id: vpn-b0fbe4a2
    state: absent
    region: us-west-2
    tags: { "Name": "example_vpn_connection" }

# Try to delete vpn_connection by Tag (Depends on Unique Keys)
- local_action:
    module: ec2_vpn_connection
    state: absent
    region: us-west-2
    tags: { "Name": "example_vpn_connection" }

"""

import sys
import os


try:
    import boto
    import boto.vpc
    import boto.vpc.vpnconnection
    from boto.regioninfo import RegionInfo
except ImportError:
    print "failed=True msg='boto required for this module'"
    sys.exit(1)


class VPNConnectionManager(object):
    """Handles VPC connection creation and destruction"""

    def __init__(self, module, id=None, type=None, cgw=None, vpn_gw=None, vpc=None, 
                 static_routes_only=None, static_routes=None, tags=None, region=None, **aws_connect_params ):

        self.module = module
        self.id = id
        self.type = type
        self.cgw = cgw
        self.vpn_gw = vpn_gw
        self.vpc = vpc
        self.static_routes_only = static_routes_only
        self.static_routes = static_routes
        self.tags = tags

        self.region = region
        self.aws_connect_params = aws_connect_params

        self.changed = False
        self.status = 'gone'
        self.aws_conn = self._get_aws_connection()
        self.vpn_conn = self._get_vpn_connection()

    def ensure_ok(self):
        """Create the vpnconnection"""
        if not self.vpn_conn:
            self._create_vpn_conn()
            #self._set_tags()

        #Update tags no matter what (need to make declaritive though)        
        self._set_tags()


    def ensure_gone(self):
        """Destroy the VPN connection"""

        if self.vpn_conn:
            #self.module.fail_json(msg="self.vpn_conn true: Attempting to delete vpnconnection")
            self._delete_vpn_conn()


    def get_info(self):
        try:
            check_aws = self.aws_conn.get_all_vpn_connections( vpn_connection_ids = [ self.id ] )[0]
        except:
            check_aws = None

        if not check_aws:
            info = {
                'id': self.id,
                'status': self.status
            }
        else:
            #typing tunnels as string because json.dumps complains 
            # "<class 'boto.resultset.ResultSet'> is not JSON serializable

            info = {
                'id': check_aws.id,
                'state': check_aws.state,
                'customer_gateway_configuration': check_aws.customer_gateway_configuration,
                'type': check_aws.type,
                'customer_gateway_id': check_aws.customer_gateway_id,
                'vpn_gateway_id': check_aws.vpn_gateway_id,
                'tunnels': str(check_aws.tunnels),
                'options': check_aws.options,
                'static_routes': check_aws.static_routes,
                'status': self.status,
            }

        return info

    def _get_vpn_connection(self):

        #self.module.fail_json(msg="aws_conn: " + str(self.aws_conn) )

        vpn_conns = self.aws_conn.get_all_vpn_connections()
        found_vpn_conns = []

        # search by id
        if self.id:
            for vpn_conn in vpn_conns:
                #self.module.fail_json(msg="vpn_conn_id: " + str(vpn_conn.id) )
                if self.id == vpn_conn.id:
                    self.status = 'ok'
                    return vpn_conn

        # Else search for tags
        elif self.tags:
            for vpn_conn in vpn_conns:
                    # Get all tags for each of the found VPCs
                    vpn_conn_tags = dict((t.name, t.value) for t in self.aws_conn.get_all_tags(filters={'resource-id': vpn_conn.id}))

                    # If the supplied list of ID Tags match a subset of the VPN Tags, we found our VPN
                    if self.tags and set(self.tags.items()).issubset(set(vpn_conn_tags.items())):
                        found_vpn_conns.append(vpn_conn)

            #vpn_conn = None

            if len(found_vpn_conns) == 1:
                vpn_conn = found_vpn_conns[0]
                self.id = vpn_conn.id
                self.status = 'ok'
                return vpn_conn

            if len(found_vpn_conns) > 1:
                self.module.fail_json(msg='Found more than one vpn connection based on the supplied criteria, aborting')

            #self.module.fail_json(msg="vpn_conns: " + str(vpn_conns) )

    def _create_vpn_conn(self):

        self.vpn_conn = self.aws_conn.create_vpn_connection(
                                                            type=self.type, 
                                                            customer_gateway_id=self.cgw, 
                                                            vpn_gateway_id=self.vpn_gw, 
                                                            static_routes_only=self.static_routes_only  
                                                            )
        if self.vpn_conn:
            self.changed = True
            self.status = 'created'
            self.id=self.vpn_conn.id


    def _delete_vpn_conn(self):
        # True if succeeds, exception raised if not
        result = self.aws_conn.delete_vpn_connection(self.id)
        if result:
            self.changed = True
            self.status = 'deleted'

    def _set_static_routes(self):        
        for route in self.static_routes:
            result = self.aws_conn.create_vpn_connection_route( 
                                                            destination_cidr_block=route, 
                                                            vpn_connection_id=self.id, 
                                                            dry_run=False 
                                                           )
            if result:
                self.changed = True

    def _delete_static_routes(self):
        for route in self.static_routes:
            result = self.aws_conn.delete_vpn_connection_route( 
                                                                destination_cidr_block=self.destination_cidr_block, 
                                                                vpn_connection_id=self.id, 
                                                                dry_run=False 
                                                               )
            if result:
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
            state={'required': True, 'choices': ['present', 'absent']},
            id={'default': None, 'required': False, 'type': 'str'},
            type={'default': 'ipsec.1', 'required': False, 'type': 'str'},
            cgw={'default': None, 'required': False, 'type': 'str'},
            vpn_gw={'default': None, 'required': False, 'type': 'str'},
            vpc={'default': None, 'required': False, 'type': 'str'},
            static_routes_only={'default': False, 'required': False, 'type': 'bool'},
            static_routes={'default': None, 'required': False, 'type': 'list' },
            tags={'required': True, 'type': 'dict'}


        )
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
    )


    region, ec2_url, aws_connect_params = get_aws_connection_info(module)


    state = module.params['state']
    id = module.params['id']
    type = module.params['type']
    cgw = module.params['cgw']
    vpn_gw = module.params['vpn_gw']
    vpc = module.params['vpc']
    static_routes_only = module.params['static_routes_only']
    static_routes = module.params['static_routes']
    tags = module.params['tags']


    if not region:
        module.fail_json(msg="Region must be specified as a parameter, in EC2_REGION or AWS_REGION environment variables or in boto configuration file")


    vpn_conn_man = VPNConnectionManager( module, id, type, cgw, vpn_gw, vpc, 
                                         static_routes_only, static_routes, tags,
                                         region, **aws_connect_params )
 
    if state == 'present':
        vpn_conn_man.ensure_ok()
    elif state == 'absent':
        vpn_conn_man.ensure_gone()


    ansible_facts = {'ec2_vpn_connection': 'info'}
    ec2_facts_result = dict(changed=vpn_conn_man.changed,
                            vpn_conn=vpn_conn_man.get_info(),
                            ansible_facts=ansible_facts)

    module.exit_json(**ec2_facts_result)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

main()
