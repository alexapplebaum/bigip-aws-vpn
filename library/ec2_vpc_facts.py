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

DOCUMENTATION = '''
---
module: vpc_facts
short_description: Gets virtual private cloud facts
description:
    - Create or term  This module has a dependency on python-boto.
version_added: "X.X"
options:
    vpc_id:
	description: 
	    - vpc id
	required: true
	default: null
	aliases: []
    include:
        description:
            - Fact category or list of categories to collect
        required: true
        default: null
        choices: [ 'vpcs', 'route_tables', 'network_acls', 'internet_gateways, 
		   'customer_gateways, 'vpn_gateways', 'subnets', 'dhcp_options',
                   'vpn_connections', 'vpc_peering_connections']
        aliases: []
    filter:
        description:
	    - EC2 type filter.ex { vpc_id
	    
            #- Shell-style glob matching string used to filter fact keys. Not
            #  applicable for software and system_info fact categories.
        required: false
        default: null
        choices: []
        aliases: []
    aws_secret_key:
	description:
	- AWS secret key. If not set then the value of the AWS_SECRET_KEY environment variable is used.
	required: false
	default: None
	aliases: ['ec2_secret_key', 'secret_key' ]
    aws_access_key:
	description:
	- AWS access key. If not set then the value of the AWS_ACCESS_KEY environment variable is used.
	required: false
	default: None
	aliases: ['ec2_access_key', 'access_key' ]
	validate_certs:
    description:
      - When set to "no", SSL certificates will not be validated for boto versions >= 2.6.0.
    required: false
    default: "yes"
    choices: ["yes", "no"]
    aliases: []
    version_added: "1.5"

requirements: [ "boto" ]
'''

EXAMPLES = '''

### playbook task examples:

---
# file gather_facts_test.yml
# ...
- hosts: vpc
  tasks:
  - name: Collect VPC facts
    vpc_facts:
      vpc: vpc_id
      user: admin
      password: mysecret
      include: subnet

'''


import sys
import time
import fnmatch
import re
import string

try:
    import boto.ec2
    import boto.vpc
    from boto.exception import EC2ResponseError
except ImportError:
    print "failed=True msg='boto required for this module'"
    sys.exit(1)

class JSONify:
    def to_JSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, 
            sort_keys=True, indent=4)

def get_vpc_info(vpc):
    """
    Retrieves vpc information from an instance
    ID and returns it as a dictionary
    """

    return({
        'id': vpc.id,
        'cidr_block': vpc.cidr_block,
        'dhcp_options_id': vpc.dhcp_options_id,
        'region': vpc.region.name,
        'state': vpc.state,
    })

def find_vpc(module, vpc_conn, vpc_id=None, cidr=None, tags=None):
    """
    Finds a VPC that matches a specific id or cidr + tags

    module : AnsibleModule object
    vpc_conn: authenticated VPCConnection connection object

    Returns:
        A VPC object that matches either an ID or CIDR and one or more tag values
    """

    if vpc_id == None and cidr == None:
        module.fail_json(
            msg='You must specify either a vpc_id or a cidr block + list of unique tags, aborting'
        )

    found_vpcs = []

    resource_tags = module.params.get('resource_tags')

    # Check for existing VPC by cidr_block or id
    if vpc_id is not None:
        found_vpcs = vpc_conn.get_all_vpcs(None, {'vpc-id': vpc_id, 'state': 'available',})

    else:
        previous_vpcs = vpc_conn.get_all_vpcs(None, {'cidr': cidr, 'state': 'available'})

        for vpc in previous_vpcs:
            # Get all tags for each of the found VPCs
            vpc_tags = dict((t.name, t.value) for t in vpc_conn.get_all_tags(filters={'resource-id': vpc.id}))

            # If the supplied list of ID Tags match a subset of the VPC Tags, we found our VPC
            if resource_tags and set(resource_tags.items()).issubset(set(vpc_tags.items())):
                found_vpcs.append(vpc)

    found_vpc = None

    if len(found_vpcs) == 1:
        found_vpc = found_vpcs[0]

    if len(found_vpcs) > 1:
        module.fail_json(msg='Found more than one vpc based on the supplied criteria, aborting')

    return (found_vpc)

def get_vpc_subnet ( vpc_conn, filters=None):
    """
    Finds a subnet that matches a specific id or cidr + tags

    module : AnsibleModule object
    vpc_conn: authenticated VPCConnection connection object

    Returns:
        Subnets ID that matches either one or more tag values
      
    """
        
    returned_subnets = vpc_conn.get_all_subnets(filters=filters)
    # get_all_subnets returns following format  
    # output = {'subnets': [Subnet:subnet-5e442229, Subnet:subnet-2363cf08, Subnet:subnet-2f63cf04, 
    # Subnet:subnet-5d44222a, Subnet:subnet-5f442228, Subnet:subnet-2d63cf06]}
    # "Subnet:subnet-5e442229" is an nested object and json.dumps pukes on it
    # Need to use jsonpickle or something but will just require a filter to return one object for now
    subnet=returned_subnets[0].id
    
    return (subnet)

# class Subnets(object):
#     """Subnets class.
# 
#     VPC Subnets class.
# 
#     Attributes:
#         
#     """
# 
#     def __init__(self, vpc_conn, regex=None):
#         self.vpc_conn = vpc_conn
#         if regex:
#             re_filter = re.compile(regex)
#             self.rules = filter(re_filter.search, self.rules)
# 

def get_vpc_route_table ( vpc_conn, filters=None):
    """
    Finds a Route Table that matches a specific tag

    module : AnsibleModule object
    vpc_conn: authenticated VPCConnection connection object

    Returns:
        Route Table ID that matches either one or more tag values
      
    """
        
    returned_route_tables = vpc_conn.get_all_route_tables(filters=filters)
    # ex. vpc_conn.get_all_route_tables(filters={'association.subnet-id':'subnet-77b20e5c'})
    route_table=returned_route_tables[0].id
    
    return (route_table)


def main():
    argument_spec = ec2_argument_spec()
    argument_spec.update(dict(
            vpc_id = dict(type='str', required=False),
            include = dict(type='list', required=False),
            filter = dict(type='dict', required=False),
            resource_tags = dict(type='dict', required=False),
        )
    )

    module = AnsibleModule(
        argument_spec = argument_spec,
    )

    vpc_id = module.params['vpc_id']
    fact_filter = module.params['filter']
    resouce_tags = module.params['resource_tags']

#     if fact_filter:
#         regex = fnmatch.translate(fact_filter)
#     else:
#         regex = None
# 
# failed: [localhost] => {"failed": true, "parsed": false}
# Traceback (most recent call last):
#   File "/Users/applebaum/.ansible/tmp/ansible-tmp-1426625761.63-253088043561025/vpc_facts", line 2054, in <module>
#     main()
#   File "/Users/applebaum/.ansible/tmp/ansible-tmp-1426625761.63-253088043561025/vpc_facts", line 217, in main
#     regex = fnmatch.translate(fact_filter)
#   File "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/fnmatch.py", line 90, in translate
#     c = pat[i]
# 

    include = map(lambda x: x.lower(), module.params['include'])
    valid_includes = ( 'vpcs', 'route_tables', 'network_acls', 'internet_gateways',
		       'customer_gateways', 'vpn_gateways', 'subnets', 'dhcp_options',
		       'vpn_connections', 'vpc_peering_connections')

    include_test = map(lambda x: x in valid_includes, include)
    if not all(include_test):
        module.fail_json(msg="value of include must be one or more of: %s, got: %s" % (",".join(valid_includes), ",".join(include)))


    module = AnsibleModule(
        argument_spec=argument_spec,
    )

    ec2_url, aws_access_key, aws_secret_key, region = get_ec2_creds(module)

    # If we have a region specified, connect to its endpoint.
    if region:
        try:
            vpc_conn = boto.vpc.connect_to_region(
                region,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key
            )
   
        except boto.exception.NoAuthHandlerFound, e:
            module.fail_json(msg = str(e))
    else:
        module.fail_json(msg="region must be specified")

    vpc_facts ={} 

    #filters will just entail resource tags for now 
    #filters={ 'vpc_id': vpc.id }
    #filters={ 'vpc_id': vpc.id, 'cidr': network }
    if 'vpcs' in include:
	return_vpcs = get_vpc( vpc_conn, filters=fact_filter  )
	vpc_facts['vpcs'] = return_vpc 

    if 'subnets' in include:
	return_subnet = get_vpc_subnet( vpc_conn, filters=fact_filter  )
	vpc_facts['subnets'] = return_subnet 

    if 'route_tables' in include:
	return_rt = get_vpc_route_table( vpc_conn, filters=fact_filter  )
	vpc_facts['route_tables'] = return_rt 
   
 
    vpc_facts_results = dict(changed=False, ansible_facts=vpc_facts) 



    module.exit_json(**vpc_facts_results)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

main()
