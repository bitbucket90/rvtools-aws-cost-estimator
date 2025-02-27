"""Data processing module for RVTools to AWS Cost Estimator."""

import csv
import logging
import pandas

# Constants for tab names
CPU_TAB = 'vCPU'
DISK_TAB = 'vDisk'


def excel_to_csv(excel_file, tab_name, output_csv_file):
    """
    Given an excel file and a tab name in it, generate an output csv file from that tab.
    
    Args:
        excel_file: The input excel file
        tab_name: The name of the tab you wish to have exported
        output_csv_file: The name of the output csv file where the tab is exported
    
    Raises:
        ValueError: If the tab_name doesn't exist in the Excel file
        Exception: For other Excel processing errors
    """
    assert excel_file and tab_name and output_csv_file
    
    # Read the Excel file with the 'openpyxl' engine and extract the specified tab
    data_xls = pandas.read_excel(excel_file, sheet_name=tab_name, engine='openpyxl')
    data_xls.to_csv(output_csv_file, encoding='utf-8', index=False)


def get_csv_column_title(title_row, *titles):
    """
    Find the column number containing a given word in the header line
    
    Args:
        title_row: The header row of a csv file
        titles: The word(s) we are searching for
        
    Returns:
        The column number
        
    Raises:
        ValueError: If no matching column is found
    """
    assert title_row and titles
    for title in titles:
        for column, value in enumerate(title_row):
            if title.lower() in value.lower().strip():  # Changed from exact match to partial match
                return column
    raise ValueError('No column header found containing: ' + str(titles))


def set_minimum_ram_size_for_instance(ram, min_ram):
    """
    Given a ram size in thousands of megabytes, in string form, and containing commas, refactor it to a single
    float value in gigabytes
    
    Args:
        ram: The string values representing thousands of megabytes
        min_ram: The minimum acceptable RAM size
        
    Returns:
        The minimum acceptable size or the initial value, whichever is larger
    """
    gig_ram = float(round(int(ram)/1000))
    return float(gig_ram if gig_ram > min_ram else min_ram)


def load_host_records_from_csv(input_csv, min_cpu):
    """
    Given a csv file of host information, load it into a list
    
    Args:
        input_csv: The input CSV file
        min_cpu: The minimum CPU size to consider
        
    Returns:
        The list of host records
    """
    assert input_csv
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
                "RAM": row[ram_column],  # We'll process this further when we have min_ram
                "VM": row[vm_column],
                "OS": row[os_column]
            })
    return hosts


def process_host_ram(hosts, min_ram):
    """
    Process RAM values for host records
    
    Args:
        hosts: List of host records
        min_ram: Minimum RAM size
        
    Returns:
        Processed host records with RAM in GB
    """
    for host in hosts:
        host["RAM"] = set_minimum_ram_size_for_instance(host["RAM"].replace(',', ''), min_ram)
    return hosts


def load_storage_records_from_csv(input_csv):
    """
    Given a csv file with storage information, load it into a list
    
    Args:
        input_csv: The input csv file
        
    Returns:
        A list of storage records
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
                    logging.warning(f"Warning: {str(e)}. Available columns: {', '.join(row)}")
                    logging.warning("Skipping storage records due to missing column.")
                    return []
                disk_row_count += 1
                continue

            disks.append({
                "Capacity": row[capacity_column],
                "VM": row[vm_column]
            })
    return disks