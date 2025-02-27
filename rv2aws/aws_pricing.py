"""AWS pricing module for RVTools to AWS Cost Estimator."""

import json
import logging
import boto3
import botocore
from collections import Counter
from functools import lru_cache


@lru_cache(maxsize=None)  # Unbounded cache
def get_storage_cost():
    """
    Return the price per unit storage cost for us-east-1
    
    Returns:
        Cost in US Dollars
        
    Raises:
        ValueError: If no price information is found
    """
    price = 0
    pricing = boto3.client('pricing', region_name='us-east-1')
    response = pricing.get_products(
        ServiceCode='AmazonEC2',
        Filters=[
            {
                "Type": "TERM_MATCH",
                "Field": "productFamily",
                "Value": "Storage"
            },
            {
                'Type': 'TERM_MATCH',
                'Field': 'volumeType',
                'Value': 'General Purpose'
            },
            {
                'Type': 'TERM_MATCH',
                'Field': 'location',
                'Value': 'US East (N. Virginia)'
            }])
    
    # Iterate through the pricelist and extract the price
    for pricelist_item in response['PriceList']:
        price_info = json.loads(pricelist_item)
        for on_demand in price_info["terms"]["OnDemand"].keys():
            for price_dimension in price_info["terms"]["OnDemand"][on_demand]["priceDimensions"]:
                price = price_info["terms"]["OnDemand"][on_demand]["priceDimensions"][price_dimension]["pricePerUnit"]
                return float(price['USD'])
    raise ValueError('No price information found for the specified criteria')


# Get current AWS price for an onDemand instance
@lru_cache(maxsize=None)  # Unbounded cache
def get_price(instance, os, pricing_model):
    """
    Get the price for an AWS instance
    
    Args:
        instance: The instance type
        os: The operating system
        pricing_model: The pricing model ("onDemand", "1-year Reserved", "3-year Reserved")
        
    Returns:
        The price as a float
    """
    pricing = boto3.client('pricing', region_name='us-east-1')
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    # Map the OS to AWS pricing categories
    os_map = {
        "CentOS": "Linux/UNIX",
        "Red Hat": "Red Hat Enterprise Linux",
        "Windows": "Windows",
        "SUSE": "SUSE Linux",
    }
    
    os_type = next((v for k, v in os_map.items() if k in os), "Linux/UNIX")

    if pricing_model == "onDemand":
        try:
            response = pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance},
                    {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': os_type},
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'},
                    {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                    {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'},
                ]
            )

            if 'PriceList' in response and response['PriceList']:
                price_info = json.loads(response['PriceList'][0])
                on_demand_prices = price_info.get('terms', {}).get('OnDemand', {})
                if on_demand_prices:
                    price_dimension = next(iter(next(iter(on_demand_prices.values())).get('priceDimensions', {}).values()))
                    price_per_unit = price_dimension.get('pricePerUnit', {}).get('USD', 0.0)
                    return float(price_per_unit)
            
            logging.warning(f"No pricing information found for {instance} with OS {os_type}")
            return 0.0

        except botocore.exceptions.ClientError as e:
            logging.error(f"API error for instance {instance}: {str(e)}")
            return 0.0

    else:  # For 1-year and 3-year Reserved instances
        offering_type = "All Upfront"
        min_duration = 31536000 if pricing_model == "1-year Reserved" else 94608000

        try:
            resp = ec2.describe_reserved_instances_offerings(
                InstanceType=instance,
                ProductDescription=os_type,
                OfferingType=offering_type,
                MinDuration=min_duration,
                MaxResults=100,
            )

            if 'ReservedInstancesOfferings' in resp and resp['ReservedInstancesOfferings']:
                reserved_instance = resp['ReservedInstancesOfferings'][0]
                return float(reserved_instance.get('FixedPrice', 0.0))

            logging.warning(f"No reserved instance offerings found for {instance} with OS {os_type}")
            return 0.0

        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterValue':
                logging.warning(f"Invalid instance type or OS: {instance}, {os_type}")
            else:
                logging.error(f"API error for reserved instance {instance}: {str(e)}")
            return 0.0

    return 0.0


def get_least_expensive_option(instances, os, pricing_model, invalid_instance_types_count):
    """
    Find the least expensive option from a list of instances
    
    Args:
        instances: List of instance types
        os: Operating system
        pricing_model: Pricing model
        invalid_instance_types_count: Counter to track invalid instance types
        
    Returns:
        Tuple with instance price info and list of invalid instances
    """
    if not instances:
        logging.error(f"No instances provided for OS: {os}, pricing model: {pricing_model}")
        return {"Instance Type": None, "Instance Cost": None}, []
    if not os:
        logging.error(f"No OS provided for instances: {instances}, pricing model: {pricing_model}")
        return {"Instance Type": None, "Instance Cost": None}, []
    
    prices = {}
    invalid_instances = []

    for instance in instances:
        price = get_price(instance, os, pricing_model)
        if price is None or price == 0.0:
            invalid_instances.append(instance)
            invalid_instance_types_count[instance] += 1
        else:
            prices[instance] = price

    sorted_prices = sorted([(k, v) for k, v in prices.items() if v is not None], key=lambda x: int(x[1]))

    if sorted_prices:
        return {"Instance Type": sorted_prices[0][0], "Instance Cost": int(sorted_prices[0][1])}, invalid_instances
    else:
        logging.warning(f"No valid prices found for instances: {instances}, OS: {os}, pricing model: {pricing_model}")
        return {"Instance Type": None, "Instance Cost": None}, invalid_instances


def get_three_year_storage_cost(host, disks):
    """
    Given a host record, return the record with storage costs appended
    
    Args:
        host: A host record
        disks: A collection of storage disk values to use for price calculations
        
    Returns:
        The host record with storage costs added
    """
    assert host and disks
    price_per_gb_month = get_storage_cost()
    vm = host['VM']
    mbytes = 0
    for disk in disks:
        if disk['VM'] == vm:
            mbytes = int(str(disk['Capacity']).replace(',', ''))
    # Convert to gigabytes
    gbytes = int(mbytes) / 1000
    monthly_cost = '%.2f' % (float(float(price_per_gb_month) * float(gbytes)))
    yearly_cost = float(monthly_cost) * 12
    three_year_cost = '%.2f' % (float(yearly_cost) * 3)
    return {"Storage": gbytes, "Storage Cost": float(three_year_cost)}


def get_total_cost(host):
    """
    Add the instance costs and the storage costs to create a total value
    
    Args:
        host: A host record containing the cost values
        
    Returns:
        A dictionary with the total value
    """
    assert host
    instance_cost = float(host["Instance Cost"]) if host["Instance Cost"] is not None else 0.0
    storage_cost = float(host["Storage Cost"]) if host["Storage Cost"] is not None else 0.0
    total = '%.2f' % (instance_cost + storage_cost)
    return {"Total": float(total)}