"""PDF generation module for RVTools to AWS Cost Estimator."""

import logging
from collections import Counter

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing


def create_pdf_quote(output_pdf_file, host_records, threshold_percentage=5):
    """
    Create a PDF quote with AWS migration costs
    
    Args:
        output_pdf_file: Path to output PDF file
        host_records: List of host records with cost information
        threshold_percentage: Threshold for grouping instance types in pie chart
        
    Returns:
        None
    """
    pdf = SimpleDocTemplate(output_pdf_file, pagesize=letter)
    elements = []

    # Logging
    logging.info("Starting PDF creation")

    # Title
    title = "AHEAD & AWS Migration Quote"
    title_style = getSampleStyleSheet()['Title']
    title_style.alignment = 1  # Align the title to the right
    elements.append(Paragraph(title, title_style))

    # Calculate the count of each instance type
    instance_types_counts = Counter(host.get("Instance Type", "Unknown") for host in host_records)
    total_count = sum(instance_types_counts.values())

    # Filter instance types, grouping those under a certain percentage into "Other"
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