"""Extension modules for RVTools to AWS Cost Estimator."""

# Import extensions here to register them
try:
    from rv2aws.extensions.excel_report import generate_excel_report
except ImportError:
    pass