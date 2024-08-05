#!/usr/bin/env python3
"""
   Updated 2024.08.05 brandon.pendleton@ahead.com
   Updates: Cleaned up CSV output, Added PDF output with total cost, updated pricing to include 1-year and 3-year reserved instances. Pie Chart to title page
   
   Need to clean up the piechart and title page
   
This is a quick-and-dirty utility to translate certain output tabs from a RVTools report into the equivalent
AWS instances and their costs. It makes lots of assumptions and shouldn't be considered a generalized utility. It
was created specifically for high level costing.

Input
  "instance_input_file" = The content of the "RVTools tabvcpu" tab from the RVTools report
  "storage_input_file" = The content of the "RVTools tabvdisk" tab from the RVTools report

Data Structures

  Host record
  -----------
  A host record consists of the following fields:

      CPU
      RAM
      VM (name)
      OS
      Instance Type
      Instance Cost (3 year reserved)
      Storage (amount)
      Storage Cost (for 3 years)
      Total Cost (for everything for 3 years)

  Example:
    {'CPUs': '16 ', 'RAM': '37,854 ', 'VM': 'ALGNT-TRVL101', 'OS': 'Microsoft Windows Server 2012 (64-bit)',
    'Instance Type': 'm4.4xlarge', 'Instance Cost': 25725, 'Storage': 358.4, 'Storage Cost': 1290.24, 'Total': 27015.24}


  Storage or Disk record
  ----------------------
  A storage record consists of only 2 fields. These are the name of the vm and the storage capacity of _one_ disk. Thus,
  there can be *multiple* records for the same VM because each record is for only one disk. All of these entries are
  added together to make a single value. This value is used to calculate the overall disk requirement for AWS. This is
  then added to the host record in the form of the Storage and Storage Cost fields (above)

  The fields are:
      VM name
      Storage capacity
"""
import argparse
import bisect
import csv
import json
import boto3
import pandas
import locale
import botocore
import logging
from collections import Counter
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# These are the tabs we want to extract from the main xls file
CPU = 'vCPU'
DISK = 'vDisk'

# This script can only calculate pricing for the instance types in the table below
def fetch_instance_types():
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
types = fetch_instance_types()


def find_greater_than_or_equal(a, key):
    """
     Find smallest item greater-than or equal to key.
     Raise ValueError if no such item exists.
     If multiple keys are equal, return the leftmost.
     """
    assert a and key
    i = bisect.bisect_left(a, key)
    if i == len(a):
        raise ValueError('No item found with key at or above: %r' % (key,))
    return a[i]

# Single host function for multi-threading
def process_host(host, disks):
    return find_aws_instance(host, disks)

def lookup_type(cpu, ram):
    """
    Given CPU and RAM requirements, return the instance type which matches those
    requirements

    :param cpu: The number of CPUs
    :param ram: The size of RAM
    :return: A list of instances which meet the above requirements
    """
    global types
    assert cpu and ram
    instances = []
    for itype in sorted(types, key=lambda i: (int(i['CPU']), int(i['RAM']))):
        if itype['CPU'] == cpu and itype['RAM'] == ram:
            instances.append(itype['type'])
    return instances

@lru_cache(maxsize=None) # Unbounded cache
def get_storage_cost():
    """
    Return the price per unit storage cost for us-east-1
    :return: Cost in US Dollars
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


def get_csv_column_title(title_row, *titles):
    """
    Find the column number containing a given word in the header line

    :param title_row: The header row of a csv file
    :param titles: The word(s) we are searching for
    :return: The column number
    """
    assert title_row and titles
    for title in titles:
        for column, value in enumerate(title_row):
            if title.lower() in value.lower().strip():  # Changed from exact match to partial match
                return column
    raise ValueError('No column header found containing: ' + str(titles))

def get_minimum_ram_size():
    """
    Return the minimum RAM size found in our list of instance types

    :return: The smallest RAM size
    """
    global types
    sorted_ram_types = sorted(types, key=lambda i: float(i['RAM']))
    return float(sorted_ram_types[0]['RAM'])


def get_minimum_cpu_size():
    """
    Return the minimum CPU count from our list of instance types

    :return: The smallest count of CPUs
    """
    global types
    sorted_cpu_types = sorted(types, key=lambda i: int(i['CPU']))
    return int(sorted_cpu_types[0]['CPU'])


def get_next_ram_size(sizes, ram):
    """
    Get the next largest RAM size from our list of sorted RAM sizes

    :param sizes: A set of sorted ram sizes
    :param ram: The current RAM size
    :return: The next larger RAM size
    """
    assert ram and sizes
    current = sizes.index(ram)
    current += 1
    # print("ram = " + str(ram) + " len = " + str(len(sizes)) + " current " + str(current))
    assert int(len(sizes)) > int(current)
    return sizes[current]


def get_correct_instance_size(cpu, ram):
    """
    Given RAM and CPU requirements, return the correct instance type(s) for that

    :param cpu: The number of CPUs
    :param ram: The size of RAM
    :return: The correct instance types that matches the RAM/CPU requirement
    """
    assert cpu and ram
    found = []

    min_cpu = find_greater_than_or_equal(extract_list_from_instance_types('CPU'), int(cpu))
    sorted_ram_size = extract_list_from_instance_types('RAM')
    min_ram = find_greater_than_or_equal(sorted_ram_size, float(ram))

    while not found:
        found = lookup_type(min_cpu, min_ram)
        min_ram = find_greater_than_or_equal(sorted_ram_size, get_next_ram_size(list(sorted_ram_size), min_ram))
        # print("min cpu: " + str(min_cpu) + " min ram: " + str(min_ram))
    return found


def get_aws_os_type(os):
    """
    Return the correct OS type for a pricing lookup

    :param os: The raw OS type
    :return: The appropriate type for a pricing lookup
    """
    assert os
    if 'Windows' in os:
        return 'Windows'
    return "Linux/UNIX"


# Get current AWS price for an onDemand instance
@lru_cache(maxsize=None) # Unbounded cache
def get_price(instance, os, pricing_model):
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

    :param host: A host record
    :param disks: A collection of storage disk values to use for price calculations
    :return: The host record with storage costs added
    """
    assert host and disks
    price_per_gb_month = get_storage_cost()
    vm = host['VM']
    mbytes = 0
    # print(vm)
    for disk in disks:
        if disk['VM'] == vm:
            mbytes = int(str(disk['Capacity']).replace(',', ''))
    # Convert to gigabytes
    gbytes = int(mbytes) / 1000
    monthly_cost = '%.2f' % (float(float(price_per_gb_month) * float(gbytes)))
    yearly_cost = float(monthly_cost) * 12
    three_year_cost = '%.2f' % (float(yearly_cost) * 3)
    # print("vm = " + str(vm) + " storage = " + str(gbytes) + " (GB) cost = " + str(monthly_cost))
    return {"Storage": gbytes, "Storage Cost": float(three_year_cost)}


def get_total_cost(host):
    """
    Add the instance costs and the storage costs to create a total value

    :param host: A host record containing the cost values
    :return: A dictionary with the total value
    """
    assert host
    instance_cost = float(host["Instance Cost"]) if host["Instance Cost"] is not None else 0.0
    storage_cost = float(host["Storage Cost"]) if host["Storage Cost"] is not None else 0.0
    total = '%.2f' % (instance_cost + storage_cost)
    return {"Total": float(total)}


def find_aws_instance(host, disks):
    if not host:
        logging.error("Empty host record provided")
        return None
    if 'CPUs' not in host or 'RAM' not in host:
        logging.error(f"Invalid host record: {host}")
        return None

    cpu = host['CPUs']
    ram = host['RAM']
    instances = get_correct_instance_size(cpu, ram)
    
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


def extract_list_from_instance_types(key):
    """
    Given a key, return a list of sorted values for that key

    :param key: Either 'CPU' or 'RAM'
    :return: A sorted list of the values found for that key
    """
    assert key
    global types
    values = set()
    for instance_type in types:
        values.add(instance_type[key])
    return sorted(values)


def set_minimum_ram_size_for_instance(ram):
    """
    Given a ram size in thousands of megabytes, in string form, and containing commas, refactor it to a single
    float value in gigabytes

    :param ram: The string values representing thousands of megabytes
    :return: The minimum acceptable size or the initial value, whichever is larger
    """
    min_ram = get_minimum_ram_size()
    gig_ram = float(round(int(ram)/1000))
    return float(gig_ram if gig_ram > min_ram else min_ram)


def load_host_records_from_csv(input_csv):
    """
    Given a csv file of host information, load it into a list

    :param input_csv: The input CSV file
    :return: The list of host records
    """
    assert input_csv
    min_cpu = get_minimum_cpu_size()
    row_count = 0
    hosts = []
    with open(input_csv, mode='r') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            if row_count == 0:
                cpu_count_column = get_csv_column_title(row, 'CPUs')
                ram_column = get_csv_column_title(row, 'Max')
                vm_column = get_csv_column_title(row, 'VM')
                os_column = get_csv_column_title(row, 'OS according to the configuration file')
                row_count += 1
                continue

            hosts.append({
                # Set the minimum acceptable values so we can pick the correct instance types
                "CPUs": int(min_cpu if int(row[cpu_count_column]) < min_cpu else row[cpu_count_column]),
                "RAM": set_minimum_ram_size_for_instance(row[ram_column]),
                "VM": row[vm_column],
                "OS": row[os_column]
            })
    return hosts


def load_storage_records_from_csv(input_csv):
    """
    Given a csv file with storage information, load it into a list

    :param input_csv: The input csv file
    :return: A list of storage records
    """
    assert input_csv
    disk_row_count = 0
    disks = []
    with open(input_csv) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            if disk_row_count == 0:
                try:
                    capacity_column = get_csv_column_title(row, 'Capacity MB', 'Capacity MiB', 'Capacity')
                    vm_column = get_csv_column_title(row, 'VM')
                except ValueError as e:
                    print(f"Warning: {str(e)}. Available columns: {', '.join(row)}")
                    print("Skipping storage records due to missing column.")
                    return []
                disk_row_count += 1
                continue

            disks.append({
                "Capacity": row[capacity_column],
                "VM": row[vm_column]
            })
    return disks


def write_report_file_to_csv(output_csv, hosts, disks, fieldnames):
    assert output_csv and hosts and disks
    total_on_demand = total_one_year = total_three_year = 0

    with open(output_csv, mode='w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for host in hosts:
            instance = find_aws_instance(host, disks)
            row = {
                'VM': instance['VM'],
                'Instance Type': instance['Instance Type'],
                'Instance Cost': instance['Instance Cost'],
                'Storage': instance['Storage'],
                'Storage Cost': instance['Storage Cost'],
                'Total': instance['Total'],
                'onDemand Cost': instance['Cost Details']['onDemand']['Instance Cost'],
                '1-Year Reserved': instance['Cost Details']['1-year Reserved']['Instance Cost'],
                '3-Year Reserved': instance['Cost Details']['3-year Reserved']['Instance Cost'],
                'Total Cost': instance['Total']
            }
            writer.writerow(row)

            # Check if any of the costs are None and add them to the total only if they are not
            total_on_demand += row['onDemand Cost'] if row['onDemand Cost'] is not None else 0
            total_one_year += row['1-Year Reserved'] if row['1-Year Reserved'] is not None else 0
            total_three_year += row['Total Cost'] if row['Total Cost'] is not None else 0

        # Write totals to CSV
        writer.writerow({
            'VM': 'Total',
            'Instance Type': '',
            'onDemand Cost': total_on_demand,
            '1-Year Reserved': total_one_year,
            '3-Year Reserved': total_three_year,
            'Total Cost': total_three_year
        })


def excel_to_csv(excel_file, tab_name, output_csv_file):
    """
    Given an excel file and a tab name in it, generate an output csv file from that tab.

    :param excel_file: The input excel file
    :param tab_name: The name of the tab you wish to have exported
    :param output_csv_file: The name of the output csv file where the tab is exported
    """
    assert excel_file and tab_name and output_csv_file

    # Read the Excel file with the 'openpyxl' engine and extract the specified tab
    data_xls = pandas.read_excel(excel_file, sheet_name=tab_name, engine='openpyxl')
    data_xls.to_csv(output_csv_file, encoding='utf-8', index=False)


import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main(input_file, output_file):
    assert input_file and output_file
    cpu_input_file = '/tmp/vcpu_input.csv'
    disk_input_file = '/tmp/vdisk_input.csv'
    
    # Initialize the Counter for invalid instance types
    invalid_instance_types_count = Counter()

    # Convert the Excel tabs to CSV
    try:
        excel_to_csv(input_file, CPU, cpu_input_file)
        excel_to_csv(input_file, DISK, disk_input_file)
    except ValueError as e:
        logging.error(f"Error converting Excel to CSV: {str(e)}")
        print("Please check if the required tabs 'vCPU' and 'vDisk' exist in the input Excel file.")
        return
    except Exception as e:
        logging.error(f"Unexpected error during Excel to CSV conversion: {str(e)}")
        return

    # Load the host and disk records
    try:
        hosts = load_host_records_from_csv(cpu_input_file)
        disks = load_storage_records_from_csv(disk_input_file)
    except Exception as e:
        logging.error(f"Error loading host or disk records: {str(e)}")
        print("Error: Unable to load host or disk records. Please check the input file format.")
        return

    if not hosts or not disks:
        logging.warning("No hosts or disks loaded from input files.")
        print("Error: No host or disk records found. Please check the input file format.")
        return

    # Print starting message
    total_hosts = len(hosts)
    logging.info(f"Starting processing of {total_hosts} hosts.")
    print(f"Starting processing of {total_hosts} hosts.")

    # Process the host records and calculate costs
    processed_host_records = []
    processed_count = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(find_aws_instance, host, disks): host for host in hosts}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    processed_host_records.append(result)
                processed_count += 1
                progress_percentage = processed_count / total_hosts * 100
                print(f"Processing host {processed_count} of {total_hosts} ({progress_percentage:.2f}% complete)", flush=True, end='\r')
            except Exception as e:
                logging.error(f"Error processing host: {str(e)}")

    # Print invalid instance types
    total_invalid_instances = sum(invalid_instance_types_count.values())
    logging.info(f"{total_invalid_instances} instances have invalid types.")
    print(f"\n{total_invalid_instances} instances have the following invalid types:")
    for instance_type, count in invalid_instance_types_count.items():
        print(f"  {instance_type}: {count}")

    # Write the report to CSV
    logging.info("Processing complete. Writing to CSV.")
    print("\nProcessing complete. Writing to CSV.")
    fieldnames = ['VM', 'Instance Type', 'Instance Cost', 'Storage', 'Storage Cost', 'Total', 'onDemand Cost', '1-Year Reserved', '3-Year Reserved', 'Total Cost']
    try:
        write_report_file_to_csv(output_file, processed_host_records, disks, fieldnames)
    except Exception as e:
        logging.error(f"Error writing CSV report: {str(e)}")
        print(f"Error writing CSV report: {str(e)}")
        return

    # Create PDF quote
    output_pdf_file = "aws_migration_quote.pdf"
    try:
        create_pdf_quote(output_pdf_file, processed_host_records)
        logging.info(f"PDF quote created: {output_pdf_file}")
    except Exception as e:
        logging.error(f"Error creating PDF quote: {str(e)}")
        print(f"Error creating PDF quote: {str(e)}")

    logging.info("Processing completed successfully.")
    print("Processing completed successfully.")


def create_pdf_quote(output_pdf_file, host_records):
    pdf = SimpleDocTemplate(output_pdf_file, pagesize=letter)
    elements = []

    # Logging
    logging.info("Starting PDF creation")
    for host in host_records:
        logging.info(f"Host data: {host}")

    # Title
    title = "AHEAD & AWS Migration Quote"
    title_style = getSampleStyleSheet()['Title']
    title_style.alignment = 1  # Align the title to the right
    elements.append(Paragraph(title, title_style))

    # Calculate the count of each instance type
    instance_types_counts = Counter(host.get("Instance Type", "Unknown") for host in host_records)
    total_count = sum(instance_types_counts.values())

    # Filter instance types, grouping those under a certain percentage into "Other"
    threshold_percentage = 5  # You can adjust this threshold
    other_count = 0
    filtered_counts = {}
    for instance_type, count in instance_types_counts.items():
        if count / total_count * 100 < threshold_percentage:
            other_count += count
        else:
            filtered_counts[instance_type] = count

    if other_count > 0:
        filtered_counts["Other"] = other_count

    instance_types = list(filtered_counts.keys())
    counts = list(filtered_counts.values())

    # Create a Pie Chart
    pie_chart = Pie()
    pie_chart.data = counts
    pie_chart.labels = instance_types
    pie_chart.width = pie_chart.height = 200

    drawing = Drawing(1, 400)  # Move drawing down
    drawing.add(pie_chart)
    elements.append(drawing)
    elements.append(Spacer(1, 50))  # Add more space after the chart to accommodate it

    # Initialize the totals
    total_on_demand = total_one_year = total_three_year = 0

    # Projected Costs
    for host in host_records:
        total_one_year += host["Cost Details"]["1-year Reserved"].get("Instance Cost", 0) or 0
        total_three_year += host.get("Total", 0) or 0

    projected_costs_data = [
        ("Projected Costs (USD)", "1-Year", "3-Year"),
        ("Total", "{:,.2f}".format(total_one_year), "{:,.2f}".format(total_three_year))
    ]
    projected_costs_table = Table(projected_costs_data)
    elements.append(projected_costs_table)
    elements.append(Spacer(1, 20))  # Add some space after the projected costs
    elements.append(PageBreak())  # Add a page break after projected costs

    # Create a table to display the host records
    table_data = [["VM", "Instance Type", "onDemand Cost", "1-Year Reserved", "3-Year Reserved", "Total Cost"]]

    for host in host_records:
        row = [
            host.get("VM", "Unknown"),
            host.get("Instance Type", "Unknown"),
            "{:,.2f}".format(host["Cost Details"]["onDemand"].get("Instance Cost", 0) or 0),
            "{:,.2f}".format(host["Cost Details"]["1-year Reserved"].get("Instance Cost", 0) or 0),
            "{:,.2f}".format(host["Cost Details"]["3-year Reserved"].get("Instance Cost", 0) or 0),
            "{:,.2f}".format(host.get("Total", 0) or 0)
        ]
        table_data.append(row)
        total_on_demand += host["Cost Details"]["onDemand"].get("Instance Cost", 0) or 0

    # Add totals row
    table_data.append([
        "Total",
        "",
        "{:,.2f}".format(total_on_demand),
        "{:,.2f}".format(total_one_year),
        "{:,.2f}".format(total_three_year),
        "{:,.2f}".format(total_three_year)
    ])
    
    # Define column widths (in points)
    col_widths = (60, 120, 80, 100, 100, 80)

    # Create table with specific column widths
    table = Table(table_data, colWidths=col_widths)

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.beige),  # Exclude the last row from the beige background
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),  # Highlight the total row
        ('FONTSIZE', (0, 0), (-1, -1), 10)  # Adjust font size
    ])

    table.setStyle(table_style)

    elements.append(table)  # Add the table to the elements list
    pdf.build(elements)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Input/Output for AWS pricing')
    parser.add_argument('--input_file', default=None, help='input file name')
    parser.add_argument('--output_file', default=None, help='output file name')
    args = parser.parse_args()
    main(args.input_file, args.output_file)