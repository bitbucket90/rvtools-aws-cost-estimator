# RVTools AWS Cost Estimator Reference

## Build/Execution Commands
- Run script: `python rv2aws2multithreadtest.py --input_file path/to/rvtools_report.xlsx --output_file path/to/output.csv`
- Install dependencies: `pip install boto3 pandas openpyxl reportlab`
- AWS config setup: Follow https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#configuration

## Code Style Guidelines
- **Imports**: Standard library first, followed by third-party packages, then local modules
- **Formatting**: Use docstrings for functions and classes
- **Types**: Use assertions for parameter validation, utilize lru_cache for performance
- **Naming**: snake_case for functions and variables, CamelCase for classes
- **Error Handling**: Use appropriate exception handling with logging
- **Logging**: Use the logging module with appropriate levels (info, warning, error)
- **Documentation**: Document function parameters and return types
- **Threading**: Utilize ThreadPoolExecutor for concurrent processing of large datasets