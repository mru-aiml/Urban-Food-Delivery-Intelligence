# Data directory
Place the dataset CSV here as `zomato_cleaned.csv`.

## Source
- HuggingFace: `allenborochin/zomato_delivery_EDA` → `zomato_cleaned.csv` (~39k rows)

## Auto-download (no extra dependencies)
If no CSV is present, the backend (`preprocessing/loader.py`) downloads it **once**
via plain HTTPS using only the Python standard library (`urllib`) and caches it as
`data/zomato_cleaned.csv`. Every later run reuses the local file — no `hf://`
path, no `huggingface_hub`, no `datasets` package required.

On Windows run:
```
pip install -r requirements.txt
python -c "from preprocessing.loader import load_raw; df,_=load_raw(); print(df.shape)"
```

## Offline fallback
If the machine has no internet, place any CSV export of the dataset in this folder.
The column-mapping layer (`config.COLUMN_MAP`) adapts to actual column names.
