# RVTools to AWS Migration Cost Estimator

## Overview
This Python script automates the process of estimating AWS migration costs based on RVTools output. It takes an RVTools Excel report as input, analyzes the virtual machine specifications, and generates a detailed cost estimate for equivalent AWS instances, including storage costs.

## Features
- Converts RVTools Excel tabs to CSV for processing
- Calculates AWS instance types based on CPU and RAM requirements
- Estimates costs for on-demand, 1-year reserved, and 3-year reserved instances
- Includes storage cost calculations
- Generates a CSV report with detailed cost breakdowns
- Creates a PDF quote with a summary and detailed instance information
- Utilizes multithreading for improved performance with large datasets
- Provides progress updates during processing

## Prerequisites
- Python 3.x
- AWS account with configured credentials

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/bitbucket90/rvtools-aws-cost-estimator.git
   cd rvtools-aws-cost-estimator
   ```

2. Install required Python libraries:
   ```
   pip install boto3 pandas openpyxl reportlab
   ```

3. Configure AWS credentials following the [official AWS guide](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration).

## Usage

Run the script with the following command:

```
python rv2aws2multithreadtest.py --input_file path/to/rvtools_report.xlsx --output_file path/to/output.csv
```

Replace `path/to/rvtools_report.xlsx` with the path to your RVTools Excel report and `path/to/output.csv` with your desired output CSV file path.

## Output

The script generates two output files:

1. A CSV file (`output.csv`) containing detailed cost estimates for each virtual machine.
2. A PDF file (`aws_migration_quote.pdf`) with a summary of projected costs and a breakdown of instance types.

## Script Details

### Main Functions

- `main()`: Orchestrates the entire process, including file conversion, data processing, and report generation.
- `find_aws_instance()`: Determines the appropriate AWS instance type and calculates costs.
- `create_pdf_quote()`: Generates a PDF report with cost summaries and instance details.

### AWS Pricing

The script uses the AWS Pricing API to fetch up-to-date pricing information for various instance types and storage options.

### Multithreading

The script employs Python's `ThreadPoolExecutor` to process multiple hosts concurrently, improving performance for large datasets.

## Customization

- Adjust the `threshold_percentage` in the `create_pdf_quote()` function to modify the grouping of instance types in the pie chart.
- Modify the `TERM_MATCH` filters in the `get_price()` function to change the AWS region or other pricing parameters.

## Troubleshooting

- Ensure your RVTools Excel file contains the required "vCPU" and "vDisk" tabs.
- Check AWS credentials are correctly configured if you encounter API-related errors.
- For large datasets, consider increasing the `max_workers` parameter in the `ThreadPoolExecutor` for potentially faster processing.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Brandon Pendleton (brandon.pendleton@ahead.com) for the original script and documentation.
- The RVTools team for their excellent virtualization documentation tool.

## Contact

For any queries or support, please contact Brandon Pendleton at brandon.pendleton@ahead.com.
