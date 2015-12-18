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
module: ec2_customer_gateway
description:
  - Returns information about the customer gateway.
  - Will be marked changed when called only if state is changed.
short_description: Creates or destroys a customer gateway.
version_added: "X.X"
author: Alex Applebaum
options:
  state:
    description:
      - if state is passed, create or destroy the customer gateway
    required: true
  ip_address:
    description:
      - IP of customer gateway to add
    required: false
    default: None
    version_added: "X.X"
  id:
    description:
      - ID of customer gateway. Will list information about that gateway or delete is state is passed. 
    required: false
    default: None
    version_added: "X.X"
  tags: 
      description:
      - Tags for vpn gateway object. Need to at least do a name. ex. { "Name" : "Example VPC Gateway" }
    required: true
    default: None
    version_added: "X.X"
  bgp_asn:
    description:
      - BGP ASN (integer)
    required: false
  type: 
    description: 
      - type of ipsec. Currently there is only one by default "ipsec.1"
    default: ipsec.1
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
    module: ec2_customer_gateway
    state: present
    ip_address: 1.1.1.1
    bgp_asn: 65000
    region: us-west-2
    tags: { "Name": "example_cgw_w_bgp" }

- local_action:
    module: ec2_customer_gateway
    state: present
    ip_address: 1.1.1.1
    region: us-west-2
    tags: { "Name": "example_cgw" }


# Ensure customer_gateway is deleted (by ID)
- local_action:
    module: ec2_customer_gateway
    id: cgw-ec60bff4
    state: absent
    region: us-west-2
    tags: { "Name": "example_cgw_w_bgp" }


"""

import sys
import os

try:
    import boto
    import boto.vpc
    import boto.vpc.customergateway
    from boto.regioninfo import RegionInfo
except ImportError:
    print "failed=True msg='boto required for this module'"
    sys.exit(1)


class CustomerGatewayManager(object):
    """Handles Customer Gateway creation and destruction"""

    #def __init__(self, module, ip_address=None, id=None, bgp_asn=None, type=None, region=None, aws_access_key=None, aws_secret_key=None):

    def __init__(self, module, ip_address=None, id=None, bgp_asn=None, type=None, tags=None, region=None, **aws_connect_params ):

        self.module = module
        self.ip_address = ip_address
        self.id = id
        self.bgp_asn = bgp_asn
        self.type = type
        self.tags = tags

        self.region = region
        #self.aws_access_key = aws_access_key
        #self.aws_secret_key = aws_secret_key
        self.aws_connect_params = aws_connect_params

        self.changed = False
        self.status = 'gone'
        self.aws_conn = self._get_aws_connection()
        self.cgw = self._get_customer_gateway()

    def ensure_ok(self):
        """Create the customergateway"""
        if not self.cgw:
            self._create_cgw()
            #self._set_tags()

        #Update tags no matter what (need to make declaritive though)     
        self._set_tags()


    def ensure_gone(self):
        """Destroy the Customer Gateway"""
        if self.cgw:
            #self.module.fail_json(msg="self.cgw true: Attempting to delete customergateway")
            self._delete_cgw()


    def get_info(self):
        try:
            if self.id:
                check_aws = self.aws_conn.get_all_customer_gateways( customer_gateway_ids = [ self.id ] )[0]
            elif self.ip_address:
                check_aws = self.aws_conn.get_all_customer_gateways( filters = { "ipAddress": self.ip_address } )[0]
        except:
            check_aws = None

        if not check_aws:
            info = {
                'ip_address': self.ip_address,
                'id': self.id,
                'status': self.status
            }
        else:
            info = {
                'ip_address': check_aws.ip_address,
                'id': check_aws.id,
                'bgp_asn': check_aws.bgp_asn,
                'type': check_aws.type,
                'status': self.status
            }

        return info

    def _get_customer_gateway(self):
        #self.module.fail_json(msg="aws_conn: " + str(self.aws_conn) )

        cgws = self.aws_conn.get_all_customer_gateways()
        found_cgws = []

        #self.module.fail_json(msg="cgws: " + str(cgws) )
        # search by id
        if self.id:
            for cgw in cgws:
                #self.module.fail_json(msg="cgw.id: " + str(cgw.id) )
                if self.id == cgw.id:
                    self.status = 'ok'
                    return cgw

        # Else search for tags
        elif self.tags:
            for cgw in cgws:
                    # Get all tags for each of the found VPCs
                    cgw_tags = dict((t.name, t.value) for t in self.aws_conn.get_all_tags(filters={'resource-id': cgw.id}))

                    # If the supplied list of ID Tags match a subset of the VPN Tags, we found our VPN
                    if self.tags and set(self.tags.items()).issubset(set(cgw_tags.items())):
                        found_cgws.append(cgw)

            #cgw = None

            if len(found_cgws) == 1:
                cgw = found_cgws[0]
                self.id = cgw.id
                self.status = 'ok'
                return cgw

            if len(found_cgws) > 1:
                self.module.fail_json(msg='Found more than one customer gateway based on the supplied criteria, aborting')


    def _create_cgw(self):
        self.cgw = self.aws_conn.create_customer_gateway(   type=self.type, 
                                                            ip_address=self.ip_address,
                                                            bgp_asn=self.bgp_asn )
        if self.cgw:
            self.id=self.cgw.id
            self.changed = True
            self.status = 'created'


    def _delete_cgw(self):
        # True if succeeds, exception raised if not
        result = self.aws_conn.delete_customer_gateway(self.id)
        if result:
            self.changed = True
            self.status = 'deleted'

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

        # try:
        #     vpc_conn = boto.vpc.connect_to_region(
        #         self.region,
        #         aws_access_key_id=self.aws_access_key,
        #         aws_secret_access_key=self.aws_secret_key
        #     )
        # except boto.exception.NoAuthHandlerFound, e:
        #     module.fail_json(msg = str(e))

        
        # return vpc_conn

        try:
            return connect_to_aws(boto.vpc, self.region,
                                  **self.aws_connect_params)
        except boto.exception.NoAuthHandlerFound, e:
            self.module.fail_json(msg=str(e))


def main():
    argument_spec = ec2_argument_spec()
    argument_spec.update(dict(
            state={'required': True, 'choices': ['present', 'absent']},
            name={'required': False, 'type': 'str'},
            ip_address={'default': None, 'required': False, 'type': 'str'},
            id={'default': None, 'required': False, 'type': 'str'},
            bgp_asn={'default': None, 'required': False, 'type': 'int'},
            type={'default': 'ipsec.1', 'required': False, 'type': 'str'},
            tags={'required': True, 'type': 'dict'}
        )
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
    )


    region, ec2_url, aws_connect_params = get_aws_connection_info(module)
    #module.fail_json(msg=" region: " + str(region) + " ec2_url: " + str(ec2_url) + " aws_connect_params: " + str(aws_connect_params) )

    #ec2_url, aws_access_key, aws_secret_key, region = get_ec2_creds(module)
    #module.fail_json(msg="ec2_url: " + str(ec2_url) + " aws_access_key: " + str(aws_access_key) + " aws_secret_key: " + str(aws_secret_key) + " region: " + str(region)  )


    name = module.params['name']
    state = module.params['state']
    ip_address = module.params['ip_address']
    id = module.params['id']
    bgp_asn = module.params['bgp_asn']
    type = module.params['type']
    tags = module.params['tags']


    if not region:
        module.fail_json(msg="Region must be specified as a parameter, in EC2_REGION or AWS_REGION environment variables or in boto configuration file")

    if state == 'present' and not ip_address:
        module.fail_json(msg="IP address is required for customer gateway creation")

 
    # cgw_man = CustomerGatewayManager(module, ip_address, id, bgp_asn, type,
    #                      region=region, aws_access_key=aws_access_key, aws_secret_key=aws_secret_key )

    cgw_man = CustomerGatewayManager(   module, ip_address, id, bgp_asn, type, tags,
                                        region, **aws_connect_params )

    # check for unsupported attributes for this version of boto;
    # N/A

    #  
    if state == 'present':
        cgw_man.ensure_ok()
    elif state == 'absent':
        cgw_man.ensure_gone()


    ansible_facts = {'ec2_customer_gateway': 'info'}
    ec2_facts_result = dict(changed=cgw_man.changed,
                            cgw=cgw_man.get_info(),
                            ansible_facts=ansible_facts)

    module.exit_json(**ec2_facts_result)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

main()
