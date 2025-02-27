"""AWS instance selection module for RVTools to AWS Cost Estimator."""

import bisect
import logging
import boto3
from collections import Counter
from functools import lru_cache

from rv2aws.utils import find_greater_than_or_equal
from rv2aws.aws_pricing import (
    get_least_expensive_option,
    get_three_year_storage_cost, 
    get_total_cost
)


def fetch_instance_types():
    """
    Fetch all available EC2 instance types and their specs
    
    Returns:
        List of dictionaries with instance type information
    """
    ec2 = boto3.client('ec2', region_name='us-east-1')
    paginator = ec2.get_paginator('describe_instance_types')
    types = []
    for page in paginator.paginate():
        for instance_type in page['InstanceTypes']:
            types.append({
                "type": instance_type['InstanceType'],
                "CPU": instance_type['VCpuInfo']['DefaultVCpus'],
                "RAM": instance_type['MemoryInfo']['SizeInMiB'] / 1024
            })
    return types


def lookup_type(cpu, ram, types):
    """
    Given CPU and RAM requirements, return the instance type which matches those
    requirements
    
    Args:
        cpu: The number of CPUs
        ram: The size of RAM
        types: List of instance types
        
    Returns:
        A list of instances which meet the requirements
    """
    assert cpu and ram
    instances = []
    for itype in sorted(types, key=lambda i: (int(i['CPU']), int(i['RAM']))):
        if itype['CPU'] == cpu and itype['RAM'] == ram:
            instances.append(itype['type'])
    return instances


def get_minimum_ram_size(types):
    """
    Return the minimum RAM size found in our list of instance types
    
    Args:
        types: List of instance types
        
    Returns:
        The smallest RAM size
    """
    sorted_ram_types = sorted(types, key=lambda i: float(i['RAM']))
    return float(sorted_ram_types[0]['RAM'])


def get_minimum_cpu_size(types):
    """
    Return the minimum CPU count from our list of instance types
    
    Args:
        types: List of instance types
        
    Returns:
        The smallest count of CPUs
    """
    sorted_cpu_types = sorted(types, key=lambda i: int(i['CPU']))
    return int(sorted_cpu_types[0]['CPU'])


def get_next_ram_size(sizes, ram):
    """
    Get the next largest RAM size from our list of sorted RAM sizes
    
    Args:
        sizes: A set of sorted ram sizes
        ram: The current RAM size
        
    Returns:
        The next larger RAM size
    """
    assert ram and sizes
    current = sizes.index(ram)
    current += 1
    assert int(len(sizes)) > int(current)
    return sizes[current]


def extract_list_from_instance_types(key, types):
    """
    Given a key, return a list of sorted values for that key
    
    Args:
        key: Either 'CPU' or 'RAM'
        types: List of instance types
        
    Returns:
        A sorted list of the values found for that key
    """
    assert key
    values = set()
    for instance_type in types:
        values.add(instance_type[key])
    return sorted(values)


def get_correct_instance_size(cpu, ram, types):
    """
    Given RAM and CPU requirements, return the correct instance type(s) for that
    
    Args:
        cpu: The number of CPUs
        ram: The size of RAM
        types: List of instance types
        
    Returns:
        The correct instance types that matches the RAM/CPU requirement
    """
    assert cpu and ram
    found = []

    min_cpu = find_greater_than_or_equal(extract_list_from_instance_types('CPU', types), int(cpu))
    sorted_ram_size = extract_list_from_instance_types('RAM', types)
    min_ram = find_greater_than_or_equal(sorted_ram_size, float(ram))

    while not found:
        found = lookup_type(min_cpu, min_ram, types)
        min_ram = find_greater_than_or_equal(sorted_ram_size, get_next_ram_size(list(sorted_ram_size), min_ram))
    return found


def get_aws_os_type(os):
    """
    Return the correct OS type for a pricing lookup
    
    Args:
        os: The raw OS type
        
    Returns:
        The appropriate type for a pricing lookup
    """
    assert os
    if 'Windows' in os:
        return 'Windows'
    return "Linux/UNIX"


def process_host(host, disks, types):
    """
    Process a single host for multithreading
    
    Args:
        host: Host record
        disks: Storage record
        types: Instance types
        
    Returns:
        Processed host record with AWS instance information
    """
    return find_aws_instance(host, disks, types)


def find_aws_instance(host, disks, types):
    """
    Find an appropriate AWS instance for a host
    
    Args:
        host: Host record
        disks: Storage records
        types: Instance types
        
    Returns:
        Host record with AWS instance and cost information
    """
    if not host:
        logging.error("Empty host record provided")
        return None
    if 'CPUs' not in host or 'RAM' not in host:
        logging.error(f"Invalid host record: {host}")
        return None

    cpu = host['CPUs']
    ram = host['RAM']
    instances = get_correct_instance_size(cpu, ram, types)
    
    if not instances:
        logging.warning(f"No suitable instances found for CPU: {cpu}, RAM: {ram}")
        return None

    pricing_models = ["onDemand", "1-year Reserved", "3-year Reserved"]
    cost_details = {}
    invalid_instance_types_count = Counter()
    all_invalid_instances = []

    for pricing_model in pricing_models:
        type_and_cost, invalid_instances = get_least_expensive_option(instances, host.get('OS'), pricing_model, invalid_instance_types_count)
        all_invalid_instances += invalid_instances
        cost_details[pricing_model] = type_and_cost

    host_with_type_cost = {**host, **cost_details["3-year Reserved"]}
    storage_cost = get_three_year_storage_cost(host, disks)
    host_with_storage_cost = {**host_with_type_cost, **storage_cost}
    total_cost = get_total_cost(host_with_storage_cost)
    host_with_cost_details = {**host_with_storage_cost, **total_cost, "Cost Details": cost_details}

    return host_with_cost_details