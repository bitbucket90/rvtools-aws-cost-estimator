"""Excel report extension for RVTools to AWS Cost Estimator."""

import logging
import os
import pandas as pd
from collections import Counter

from rv2aws.main import register_extension


def generate_excel_report(processed_host_records, context):
    """
    Generate a detailed Excel report with multiple tabs
    
    Args:
        processed_host_records: List of processed host records
        context: Processing context
        
    Returns:
        None
    """
    logger = context.get('logger', logging.getLogger())
    args = context.get('args')
    
    # Determine output file path
    base_output = os.path.splitext(args.output_file)[0]
    excel_output = f"{base_output}_report.xlsx"
    
    logger.info(f"Generating Excel report: {excel_output}")
    
    # Create Excel writer
    with pd.ExcelWriter(excel_output, engine='openpyxl') as writer:
        # Create summary DataFrame
        summary_data = {
            'VM Count': [len(processed_host_records)],
            'Total CPU Cores': [sum(host.get('CPUs', 0) for host in processed_host_records)],
            'Total RAM (GB)': [sum(host.get('RAM', 0) for host in processed_host_records)],
            'Total Storage (GB)': [sum(host.get('Storage', 0) for host in processed_host_records)],
            'On-Demand Cost': [sum(host['Cost Details']['onDemand'].get('Instance Cost', 0) or 0 for host in processed_host_records)],
            '1-Year Reserved Cost': [sum(host['Cost Details']['1-year Reserved'].get('Instance Cost', 0) or 0 for host in processed_host_records)],
            '3-Year Reserved Cost': [sum(host['Cost Details']['3-year Reserved'].get('Instance Cost', 0) or 0 for host in processed_host_records)],
            'Total Cost': [sum(host.get('Total', 0) or 0 for host in processed_host_records)]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Create details DataFrame
        details_data = []
        for host in processed_host_records:
            details_data.append({
                'VM': host.get('VM'),
                'CPUs': host.get('CPUs'),
                'RAM (GB)': host.get('RAM'),
                'Storage (GB)': host.get('Storage'),
                'OS': host.get('OS'),
                'Instance Type': host.get('Instance Type'),
                'Instance Cost': host.get('Instance Cost'),
                'Storage Cost': host.get('Storage Cost'),
                'Total Cost': host.get('Total'),
                'On-Demand Cost': host['Cost Details']['onDemand'].get('Instance Cost'),
                '1-Year Reserved': host['Cost Details']['1-year Reserved'].get('Instance Cost'),
                '3-Year Reserved': host['Cost Details']['3-year Reserved'].get('Instance Cost')
            })
        details_df = pd.DataFrame(details_data)
        details_df.to_excel(writer, sheet_name='Details', index=False)
        
        # Create instance types breakdown
        instance_types = Counter(host.get('Instance Type', 'Unknown') for host in processed_host_records)
        instance_df = pd.DataFrame({
            'Instance Type': list(instance_types.keys()),
            'Count': list(instance_types.values())
        })
        instance_df = instance_df.sort_values(by='Count', ascending=False)
        instance_df.to_excel(writer, sheet_name='Instance Types', index=False)
        
        # Create OS breakdown
        os_types = Counter(host.get('OS', 'Unknown') for host in processed_host_records)
        os_df = pd.DataFrame({
            'OS': list(os_types.keys()),
            'Count': list(os_types.values())
        })
        os_df = os_df.sort_values(by='Count', ascending=False)
        os_df.to_excel(writer, sheet_name='OS Types', index=False)
    
    logger.info(f"Excel report generated: {excel_output}")


# Register the extension
register_extension('report_generators', generate_excel_report)