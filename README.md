# RVTools to AWS Migration Cost Estimator

## Overview
This Python package automates the process of estimating AWS migration costs based on RVTools output. It takes an RVTools Excel report as input, analyzes the virtual machine specifications, and generates a detailed cost estimate for equivalent AWS instances, including storage costs.

## Features
- Converts RVTools Excel tabs to CSV for processing
- Calculates AWS instance types based on CPU and RAM requirements
- Estimates costs for on-demand, 1-year reserved, and 3-year reserved instances
- Includes storage cost calculations
- Generates a CSV report with detailed cost breakdowns
- Creates a PDF quote with a summary and detailed instance information
- Utilizes multithreading for improved performance with large datasets
- Provides progress updates during processing
- Modular architecture for easy extension and customization

## Prerequisites
- Python 3.6+
- AWS account with configured credentials

## Installation

### Option 1: Install from source
1. Clone the repository:
   ```
   git clone https://github.com/bitbucket90/rvtools-aws-cost-estimator.git
   cd rvtools-aws-cost-estimator
   ```

2. Install the package:
   ```
   pip install -e .
   ```

### Option 2: Install from PyPI (coming soon)
   ```
   pip install rv2aws
   ```

3. Configure AWS credentials following the [official AWS guide](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration).

## Usage

### Command Line Interface
Run the tool with the following command:

```
rv2aws --input_file path/to/rvtools_report.xlsx --output_file path/to/output.csv
```

or using the included script:

```
./rv2aws-cli.py --input_file path/to/rvtools_report.xlsx --output_file path/to/output.csv
```

### Options
- `--input_file`: Path to RVTools Excel file (required)
- `--output_file`: Path to output CSV file (required)
- `--threads`: Number of worker threads (default: 5)
- `--pdf_output`: Path to output PDF file (default: aws_migration_quote.pdf)
- `--verbose`: Enable verbose logging
- `--region`: AWS region for pricing (default: us-east-1)

## Output

The tool generates two output files:

1. A CSV file (`output.csv`) containing detailed cost estimates for each virtual machine.
2. A PDF file (`aws_migration_quote.pdf`) with a summary of projected costs and a breakdown of instance types.

## Architecture

The package is organized into modular components:

- `data_processing.py`: Handles input/output operations and data transformation
- `aws_instance.py`: Manages instance type selection logic
- `aws_pricing.py`: Interacts with AWS pricing APIs 
- `report_generator.py`: Generates CSV reports
- `pdf_generator.py`: Creates PDF quotes with visualization
- `utils.py`: Contains utility functions
- `main.py`: Orchestrates the overall process

## Extending the Tool

The modular architecture makes it easy to extend the tool:

1. To add support for new cloud providers, create a new module similar to `aws_instance.py`
2. To create new report formats, add a module similar to `pdf_generator.py`
3. To customize AWS pricing logic, modify the `aws_pricing.py` module

### Creating Extensions

The tool provides an extension mechanism through three extension points:
- `pre_process`: Runs before VM processing, allows modifying input data
- `post_process`: Runs after VM processing, allows transforming results
- `report_generators`: Runs after standard reports, adds custom report formats

Example: Create a new Excel report generator extension:

1. Create a file in `rv2aws/extensions/excel_report.py`:
   ```python
   from rv2aws.main import register_extension
   
   def generate_excel_report(processed_host_records, context):
       # Generate an Excel report with the processed data
       # ...
   
   # Register the extension
   register_extension('report_generators', generate_excel_report)
   ```

2. Import the extension in `rv2aws/extensions/__init__.py`:
   ```python
   # Import extensions here to register them
   from rv2aws.extensions.excel_report import generate_excel_report
   ```

The tool will automatically discover and run registered extensions.

## Troubleshooting

- Ensure your RVTools Excel file contains the required "vCPU" and "vDisk" tabs.
- Check AWS credentials are correctly configured if you encounter API-related errors.
- For large datasets, increase the `--threads` parameter for faster processing.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Brandon Pendleton (brandon.pendleton@ahead.com) for the original script and documentation.
- The RVTools team for their excellent virtualization documentation tool.

## Contact

For any queries or support, please contact Brandon Pendleton at brandon.pendleton@ahead.com or submit an issue or merge request on the repo.
