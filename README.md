Demo - https://drive.google.com/drive/folders/1pfOmzpqUmUpYXKq6bgS6xN4DvT0BhW0u?usp=sharing

# 🧠 Groq-Powered PDF Bank Statement Parser Agent

This project is an **autonomous Python agent** that generates a **custom parser** for bank statement PDFs using **Groq's LLM API**.

You give it:
- a sample **bank PDF**  
- an **expected CSV** output (with matching schema)  

…and it will:
1. Extract a table preview from the PDF
2. Send it to Groq with instructions to **write a parser**
3. Save that parser in `custom_parsers/<bank>_parser.py`
4. Run **pytest** to check if the parser output matches the expected CSV exactly
5. If it fails → start a repair loop for up to N attempts
6. On final failure → try a **regex+full-text fallback**
7. Save artifacts if it still fails

---

## 📂 Repository Structure

├── agent.py
├── .env # Groq API key & model name
├── custom_parsers/ # Generated parser modules
├── data/
│ └── icici/
│ ├── icici_sample.pdf
│ └── icici_expected.csv
├── tests/
│ └── test_icici.py
├── artifacts/ # Failure logs and parser snapshots
├── requirements.txt
└── README.md

---

## 🛠 Installation

1. **Clone this repository**
git clone <your_repo_url>
cd <your_repo_name>

2. **Install Python dependencies**
pip install -r requirements.txt

3. **Set up environment variables** in a `.env` file at project root:
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

4. **Ensure sample data exists** for your bank  
   For example, for ICICI:
data/icici/icici_sample.pdf
data/icici/icici_expected.csv

---

## 🚀 Usage

Generate a parser for ICICI:
python agent.py --target icici


The agent will:
- Load configuration
- Extract a structured preview from the PDF
- Ask Groq to write `custom_parsers/icici_parser.py`
- Run `pytest` to check the parser's output
- Attempt repairs if needed
- Try regex-based fallback on final failure
- Save final parser or artifacts

---

## ⚙ How It Works Internally

1. **Heuristic Table Preview**  
   Uses `pdfplumber` to read first, middle, and last pages of sample PDF

2. **Groq Codegen Prompt**  
   Sends:
   - Bank name
   - Expected CSV headers (exact order)
   - Sample table preview JSON
   - Strict parsing and value-preservation rules

3. **Testing & Repair Loop**  
   - Run tests: `assert df.astype(str).equals(expected_df.astype(str))`
   - On fail → include mismatched rows in repair prompt to Groq
   - Retry until N attempts reached

4. **Regex Fallback**  
   If still failing → send **full PDF text** to Groq, ask for regex parser

5. **Artifacts Saving**  
   Last parser code, logs, and mismatches saved in `artifacts/run-<timestamp>/`

---

## 🧮 Supported Banks

Currently supported:
- **ICICI**

Easily extend by adding:
- New sample PDF in `data/<bank>/`
- Expected CSV in same folder
- Update `BANK_CONFIG` in `agent.py`

---


