// ===================================================================================================
// Power Query (M) for the Distributed Network Monitoring dashboard.
// In Power BI Desktop:  Home > Transform data > New Source > Blank Query > Advanced Editor, paste each block.
// First create a parameter  DataFolder  (Manage parameters > New, type Text), e.g.  C:\path\to\repo\
// (keep the trailing backslash / slash). Queries: telemetry, capstone, bandwidth_order.
// ===================================================================================================

// ---- Query 1: telemetry  (120,000 rows, the lecturer's 100k+ dataset) --------------------------------
let
    Source   = Csv.Document(File.Contents(DataFolder & "data\telemetry_120k.csv"),
                            [Delimiter = ",", Columns = 17, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                  {"record_id", Int64.Type}, {"timestamp", type datetimezone}, {"site_id", type text}, {"region", type text},
                  {"edge_node", type text}, {"site_type", type text}, {"cpu_pct", type number}, {"mem_pct", type number},
                  {"rx_mbps", type number}, {"tx_mbps", type number}, {"latency_ms", type number}, {"jitter_ms", type number},
                  {"packet_loss_pct", type number}, {"active_users", Int64.Type}, {"signal_dbm", type number},
                  {"temperature_c", type number}, {"is_anomaly", Int64.Type}}, "en-US"),
    WithTs   = Table.AddColumn(Typed, "ts", each DateTimeZone.RemoveZone([timestamp]), type datetime),
    WithHour = Table.AddColumn(WithTs, "hour_start",
                  each #datetime(Date.Year([ts]), Date.Month([ts]), Date.Day([ts]), Time.Hour([ts]), 0, 0), type datetime),
    WithDay  = Table.AddColumn(WithHour, "day", each Date.From([ts]), type date),
    Result   = Table.RemoveColumns(WithDay, {"timestamp"})
in
    Result

// ---- Query 2: capstone  (Milestone 12 results: baseline vs proposed vs proposed+improved) -----------
let
    Source   = Csv.Document(File.Contents(DataFolder & "results\m12_capstone_summary.csv"),
                            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    TextCols = {"sweep", "level", "system"},
    NumCols  = List.Difference(Table.ColumnNames(Promoted), TextCols),
    Typed    = Table.TransformColumnTypes(
                  Table.TransformColumnTypes(Promoted, List.Transform(TextCols, each {_, type text})),
                  List.Transform(NumCols, each {_, type number}), "en-US")
in
    Typed
