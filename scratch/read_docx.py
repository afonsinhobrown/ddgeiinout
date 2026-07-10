import docx

def read_docx(path):
    doc = docx.Document(path)
    for i, table in enumerate(doc.tables):
        print(f"\n--- Tabela {i+1} ---")
        for j, row in enumerate(table.rows):
            if j > 3: # Limit to first 4 rows to check structure
                break
            cells = [cell.text.replace('\n', ' ').strip() for cell in row.cells]
            print(f"Linha {j+1}: {cells}")

if __name__ == "__main__":
    read_docx(r"c:\Users\Acer\Documents\tecnologias\ddgeiinout\Material_Recenseamento_Eleitoral_A3 (2).docx")
