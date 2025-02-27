"""Main module for RVTools to AWS Cost Estimator."""

import argparse
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

from rv2aws.utils import setup_logging
from rv2aws.data_processing import (
    CPU_TAB, DISK_TAB, excel_to_csv, load_host_records_from_csv, 
    process_host_ram, load_storage_records_from_csv
)
from rv2aws.aws_instance import (
    fetch_instance_types, get_minimum_cpu_size, get_minimum_ram_size,
    process_host, find_aws_instance
)
from rv2aws.report_generator import write_report_file_to_csv
from rv2aws.pdf_generator import create_pdf_quote

# Import extensions
try:
    import rv2aws.extensions
except ImportError:
    pass


def parse_arguments():
    """
    Parse command-line arguments
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description='RVTools to AWS Migration Cost Estimator')
    parser.add_argument('--input_file', required=True, help='Path to RVTools Excel file')
    parser.add_argument('--output_file', required=True, help='Path to output CSV file')
    parser.add_argument('--threads', type=int, default=5, help='Number of worker threads')
    parser.add_argument('--pdf_output', default="aws_migration_quote.pdf", help='Path to output PDF file')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--region', default='us-east-1', help='AWS region for pricing (default: us-east-1)')
    return parser.parse_args()


# Dictionary to store registered extensions
_extensions = {
    'pre_process': [],
    'post_process': [],
    'report_generators': [],
}

def register_extension(extension_point, callback):
    """
    Register an extension callback for a specific extension point
    
    Args:
        extension_point: The extension point name ('pre_process', 'post_process', 'report_generators')
        callback: The callback function to register
        
    Returns:
        None
    """
    if extension_point not in _extensions:
        raise ValueError(f"Unknown extension point: {extension_point}")
    _extensions[extension_point].append(callback)


def main():
    """
    Main function to run the cost estimator
    """
    # Parse arguments
    args = parse_arguments()
    
    # Set up logging
    logger = setup_logging(args.verbose)
    
    # Input validation
    if not os.path.isfile(args.input_file):
        logger.error(f"Input file not found: {args.input_file}")
        return 1
    
    start_time = time.time()
    
    # Create temp files for CSV conversion
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as cpu_temp, \
         tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as disk_temp:
        
        cpu_input_file = cpu_temp.name
        disk_input_file = disk_temp.name
    
    # Convert Excel tabs to CSV
    try:
        logger.info(f"Converting Excel tabs from {args.input_file}")
        excel_to_csv(args.input_file, CPU_TAB, cpu_input_file)
        excel_to_csv(args.input_file, DISK_TAB, disk_input_file)
    except ValueError as e:
        logger.error(f"Error converting Excel to CSV: {str(e)}")
        logger.error("Please check if the required tabs 'vCPU' and 'vDisk' exist in the input Excel file.")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error during Excel to CSV conversion: {str(e)}")
        return 1
    
    # Fetch instance types
    try:
        logger.info("Fetching AWS instance types")
        instance_types = fetch_instance_types()
        min_cpu = get_minimum_cpu_size(instance_types)
        min_ram = get_minimum_ram_size(instance_types)
    except Exception as e:
        logger.error(f"Error fetching AWS instance types: {str(e)}")
        return 1
    
    # Load host and disk records
    try:
        logger.info("Loading host and disk records")
        hosts = load_host_records_from_csv(cpu_input_file, min_cpu)
        hosts = process_host_ram(hosts, min_ram)
        disks = load_storage_records_from_csv(disk_input_file)
    except Exception as e:
        logger.error(f"Error loading host or disk records: {str(e)}")
        logger.error("Unable to load host or disk records. Please check the input file format.")
        return 1
    
    if not hosts or not disks:
        logger.warning("No hosts or disks loaded from input files.")
        logger.error("No host or disk records found. Please check the input file format.")
        return 1
    
    # Run pre-process extensions
    context = {
        'args': args,
        'hosts': hosts,
        'disks': disks,
        'instance_types': instance_types,
        'logger': logger
    }
    for extension in _extensions['pre_process']:
        try:
            logger.info(f"Running pre-process extension: {extension.__name__}")
            hosts, disks = extension(hosts, disks, context)
        except Exception as e:
            logger.error(f"Error in pre-process extension {extension.__name__}: {str(e)}")
    
    # Process the host records
    total_hosts = len(hosts)
    logger.info(f"Starting processing of {total_hosts} hosts")
    print(f"Starting processing of {total_hosts} hosts")
    
    processed_host_records = []
    processed_count = 0
    invalid_instance_types_count = Counter()
    
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        # Create futures for each host
        futures = {
            executor.submit(process_host, host, disks, instance_types): host 
            for host in hosts
        }
        
        # Process as they complete
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    processed_host_records.append(result)
                processed_count += 1
                progress_percentage = processed_count / total_hosts * 100
                print(f"Processing host {processed_count} of {total_hosts} "
                      f"({progress_percentage:.2f}% complete)", flush=True, end='\r')
            except Exception as e:
                logger.error(f"Error processing host: {str(e)}")
    
    print()  # New line after progress indicator
    
    # Print invalid instance types information
    total_invalid_instances = sum(invalid_instance_types_count.values())
    if total_invalid_instances > 0:
        logger.info(f"{total_invalid_instances} instances have invalid types")
        print(f"{total_invalid_instances} instances have the following invalid types:")
        for instance_type, count in invalid_instance_types_count.most_common():
            print(f"  {instance_type}: {count}")
    
    # Run post-process extensions
    context.update({
        'processed_host_records': processed_host_records,
        'invalid_instance_types_count': invalid_instance_types_count
    })
    for extension in _extensions['post_process']:
        try:
            logger.info(f"Running post-process extension: {extension.__name__}")
            processed_host_records = extension(processed_host_records, context)
        except Exception as e:
            logger.error(f"Error in post-process extension {extension.__name__}: {str(e)}")
    
    # Write the report to CSV
    logger.info("Processing complete. Writing to CSV.")
    print("Processing complete. Writing to CSV.")
    try:
        fieldnames = [
            'VM', 'Instance Type', 'Instance Cost', 'Storage', 'Storage Cost', 
            'Total', 'onDemand Cost', '1-Year Reserved', '3-Year Reserved', 'Total Cost'
        ]
        write_report_file_to_csv(args.output_file, processed_host_records, disks, instance_types, fieldnames)
    except Exception as e:
        logger.error(f"Error writing CSV report: {str(e)}")
        print(f"Error writing CSV report: {str(e)}")
        return 1
    
    # Create PDF quote
    try:
        logger.info(f"Creating PDF quote: {args.pdf_output}")
        create_pdf_quote(args.pdf_output, processed_host_records)
        logger.info(f"PDF quote created: {args.pdf_output}")
    except Exception as e:
        logger.error(f"Error creating PDF quote: {str(e)}")
        print(f"Error creating PDF quote: {str(e)}")
    
    # Run custom report generators
    for report_generator in _extensions['report_generators']:
        try:
            logger.info(f"Running custom report generator: {report_generator.__name__}")
            report_generator(processed_host_records, context)
        except Exception as e:
            logger.error(f"Error in report generator {report_generator.__name__}: {str(e)}")
    
    # Clean up temp files
    try:
        os.unlink(cpu_input_file)
        os.unlink(disk_input_file)
    except Exception as e:
        logger.warning(f"Error cleaning up temporary files: {str(e)}")
    
    elapsed_time = time.time() - start_time
    logger.info(f"Processing completed successfully in {elapsed_time:.2f} seconds")
    print(f"Processing completed successfully in {elapsed_time:.2f} seconds")
    return 0


if __name__ == '__main__':
    exit(main())