import pdfplumber
import pandas as pd
import typing

def parse(pdf_path: str) -> pd.DataFrame:
    """
    Parse an ICICI bank statement PDF and return a DataFrame with the following columns:
    ['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'].
    The function extracts tables from each page of the PDF, skips header rows,
    and ignores any rows that do not contain the expected number of columns.
    """
    data: typing.List[typing.List[str]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            for row in table:
                if row is None:
                    continue
                if len(row) < 5:
                    continue
                # Skip header rows
                if row[0] == "Date" and row[1] == "Description":
                    continue
                # Skip rows that start with 'Page' or are empty in the first column
                if row[0] is None or row[0] == "" or str(row[0]).startswith("Page"):
                    continue

                # Normalize cells: replace None or empty string with 'nan'
                cleaned = [
                    str(cell) if cell not in (None, "") else "nan" for cell in row[:5]
                ]
                data.append(cleaned)

    df = pd.DataFrame(
        data,
        columns=["Date", "Description", "Debit Amt", "Credit Amt", "Balance"],
    )
    # Ensure all columns are strings for comparison
    df = df.astype(str)
    return df
df = parse("C:/Users/VETRISELVAN S/OneDrive/Desktop/Agent/data/icici/icici_sample.pdf")
print(df.head(10))