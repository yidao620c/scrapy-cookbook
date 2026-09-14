ITEM_PIPELINES = {
    "quotesitem.pipelines.EnrichPipeline": 200,
    "quotesitem.pipelines.DedupPipeline": 300,
    "quotesitem.pipelines.JsonlPipeline": 400,
    "quotesitem.pipelines.SQLitePipeline": 500,
}

JSONL_PATH = "out/quotes_pipeline.jsonl"
SQLITE_PATH = "out/quotes.db"
