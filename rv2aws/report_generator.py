"""Report generation module for RVTools to AWS Cost Estimator."""

import csv
import logging
from rv2aws.aws_instance import find_aws_instance


def write_report_file_to_csv(output_csv, hosts, disks, types, fieldnames=None):
    """
    Write a CSV report of costs
    
    Args:
        output_csv: Path to output CSV file
        hosts: List of host records
        disks: List of disk records
        types: List of instance types
        fieldnames: Optional list of fieldnames for CSV
        
    Returns:
        Tuple of total costs (on_demand, one_year, three_year)
    """
    assert output_csv and hosts and disks
    
    if fieldnames is None:
        fieldnames = [
            'VM', 'Instance Type', 'Instance Cost', 'Storage', 'Storage Cost', 
            'Total', 'onDemand Cost', '1-Year Reserved', '3-Year Reserved', 'Total Cost'
        ]
    
    total_on_demand = total_one_year = total_three_year = 0

    with open(output_csv, mode='w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for host in hosts:
            instance = find_aws_instance(host, disks, types)
            if instance:
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
    
    return (total_on_demand, total_one_year, total_three_year)