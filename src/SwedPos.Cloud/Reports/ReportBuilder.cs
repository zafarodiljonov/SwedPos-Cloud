using System.Data;
using Microsoft.EntityFrameworkCore;
using SwedPos.Data;
using SwedPos.Domain;
using SwedPos.Services;

namespace SwedPos.Cloud.Reports;

// A report page is a list of blocks (tiles, charts, cards with tables). The builder turns the shared
// AnalyticsService results into blocks; Razor components draw them. Tables are ReportTables, the same model the
// desktop exports, so "Excel" on the website writes exactly what is on screen.

public abstract record Block;
public sealed record Tile(string Label, string Value, decimal? Change = null, bool HigherIsBetter = true, string? Note = null, bool Accent = false);
public sealed record TilesBlock(IReadOnlyList<Tile> Tiles) : Block;
public sealed record ColumnsBlock(IReadOnlyList<Block> Items) : Block;
public sealed record CardBlock(string Title, Block Content, string? Note = null, IReadOnlyList<(string Text, bool Dashed)>? Legend = null) : Block;
public sealed record Point(string Label, decimal Value, decimal? Previous = null, string? Tooltip = null);
public sealed record LineBlock(IReadOnlyList<Point> Points) : Block;
public sealed record BarBlock(IReadOnlyList<Point> Points) : Block;
public sealed record HeatBlock(IReadOnlyList<HeatCell> Cells, string[] Days, string OrdersLabel) : Block;
public sealed record SharesBlock(IReadOnlyList<(string Label, decimal Amount, decimal Percent)> Parts) : Block;
public sealed record BarsBlock(IReadOnlyList<(string Label, decimal Value, string Text)> Rows) : Block;
/// <summary>A table; with <see cref="Drill"/> a row can be opened (the key of each row is in <see cref="RowKeys"/>).</summary>
public sealed record TableBlock(ReportTable Table, string? Drill = null, IReadOnlyList<int>? RowKeys = null) : Block;
public sealed record ChipsBlock(IReadOnlyList<string> Items) : Block;
public sealed record EmptyBlock : Block;
public sealed record MonthNavBlock(DateOnly Month, string Label, string Note) : Block;

public sealed record ReportPage(IReadOnlyList<Block> Blocks, IReadOnlyList<ReportTable> Tables);

public class ReportBuilder
{
    public static readonly string[] Pages = { "overview", "sales", "payments", "waiters", "payroll", "tables", "products", "customers", "control", "stock" };

    private readonly SwedPosDbContext _db;
    private readonly string _lang;
    private readonly List<ReportTable> _tables = new();

    public ReportBuilder(SwedPosDbContext db, string lang) { _db = db; _lang = lang; }

    private string L(string key) => Texts.Get(_lang, key);
    private string Pick(string uz, string ru) => _lang == "ru" ? ru : uz;
    private static string Money(decimal v) => Fmt.Money(v);
    private ReportTable Keep(ReportTable t) { _tables.Add(t); return t; }
    private string[] Weekdays => L("an_weekdays").Split('|');
    private string MonthShort(DateOnly d) => L("an_months").Split('|')[d.Month - 1];
    public string MonthName(DateOnly d) => MonthShort(d) + " " + d.Year;

    private string MethodName(PaymentMethod m) => m switch
    {
        PaymentMethod.Cash => L("btn_pay_cash"), PaymentMethod.Card => L("btn_pay_card"),
        PaymentMethod.Transfer => L("pay_transfer_short"), _ => L("an_mixed")
    };

    private string KeyName(string key) => key switch
    {
        nameof(OrderType.DineIn) => L("report_dine_in"),
        nameof(OrderType.Takeaway) => L("order_type_takeaway"),
        nameof(OrderType.Delivery) => L("order_type_delivery"),
        _ => MethodName(Enum.Parse<PaymentMethod>(key))
    };

    public async Task<ReportPage> BuildAsync(string page, AnalyticsFilter f, DateOnly payMonth)
    {
        var blocks = page switch
        {
            "sales" => await SalesAsync(f),
            "payments" => await PaymentsAsync(f),
            "waiters" => await WaitersAsync(f),
            "payroll" => await PayrollAsync(payMonth),
            "tables" => await TablesAsync(f),
            "products" => await ProductsAsync(f),
            "customers" => await CustomersAsync(f),
            "control" => await ControlAsync(f),
            "stock" => await StockAsync(f),
            _ => await OverviewAsync(f)
        };
        return new ReportPage(blocks, _tables);
    }

    // ================= overview =================

    private async Task<List<Block>> OverviewAsync(AnalyticsFilter f)
    {
        var o = await new AnalyticsService(_db).OverviewAsync(f);
        var k = o.Kpis;
        var list = new List<Block>
        {
            new TilesBlock(new[]
            {
                new Tile(L("an_revenue"), Money(k.Revenue.Value), k.Revenue.ChangePercent, Accent: true),
                new Tile(L("an_orders"), Fmt.Int(k.Orders.Value), k.Orders.ChangePercent),
                new Tile(L("report_avg"), Money(k.AverageCheck.Value), k.AverageCheck.ChangePercent),
                new Tile(L("recipe_profit"), Money(k.Profit.Value), k.Profit.ChangePercent),
                new Tile(L("recipe_margin"), Fmt.Percent(k.MarginPercent.Value), Note: L("an_previous") + ": " + Fmt.Percent(k.MarginPercent.Previous)),
            }),
            new TilesBlock(new[]
            {
                new Tile(L("an_guests"), Fmt.Int(k.Guests.Value), k.Guests.ChangePercent),
                new Tile(L("an_per_guest"), Money(k.AveragePerGuest.Value), k.AveragePerGuest.ChangePercent),
                new Tile(L("shift_discounts"), Money(k.Discounts.Value), k.Discounts.ChangePercent, HigherIsBetter: false),
                new Tile(L("an_cancelled"), Fmt.Int(k.Cancelled.Value) + " · " + Money(k.CancelledAmount.Value), k.Cancelled.ChangePercent, HigherIsBetter: false),
                new Tile(L("an_waiter_earned"), Money(k.WaiterEarned.Value), k.WaiterEarned.ChangePercent),
            })
        };
        string Label(DateOnly d) => o.Granularity == Granularity.Month ? MonthShort(d) : d.ToString("dd.MM");
        list.Add(new CardBlock(L("an_revenue_by_" + o.Granularity.ToString().ToLowerInvariant()),
            new LineBlock(o.Series.Select(p => new Point(Label(p.Start), p.Revenue, p.PreviousRevenue,
                Label(p.Start) + "\n" + Money(p.Revenue) + "\n" + L("an_orders") + ": " + p.Orders + "\n" + L("an_previous") + ": " + Money(p.PreviousRevenue))).ToList()),
            Legend: new[] { (L("an_this_period"), false), (L("an_previous_period"), true) }));
        list.Add(new ColumnsBlock(new Block[]
        {
            new CardBlock(L("an_payments"), new SharesBlock(o.Payments.Select(p => (KeyName(p.Key), p.Amount, p.Percent)).ToList())),
            new CardBlock(L("report_types"), new SharesBlock(o.OrderTypes.Select(t => (KeyName(t.Key), t.Amount, t.Percent)).ToList()))
        }));
        list.Add(new ColumnsBlock(new Block[]
        {
            new CardBlock(L("an_top_dishes"), new BarsBlock(o.TopDishes.Select(d => (Pick(d.NameUz, d.NameRu), d.Revenue, Money(d.Revenue) + " · " + d.Quantity)).ToList())),
            new CardBlock(L("an_top_waiters"), new BarsBlock(o.TopWaiters.Select(w => (w.Name, w.Revenue, Money(w.Revenue))).ToList()))
        }));

        var series = Keep(new ReportTable(L("an_revenue")).Col(L("an_period_start"), ColumnKind.Date).Col(L("an_orders"), ColumnKind.Integer)
            .Col(L("an_revenue"), ColumnKind.Money).Col(L("an_previous_period"), ColumnKind.Money));
        foreach (var p in o.Series) series.Row(p.Start.ToDateTime(TimeOnly.MinValue), p.Orders, p.Revenue, p.PreviousRevenue);
        var kpi = Keep(new ReportTable(L("an_key_figures")).Col(L("an_figure"), ColumnKind.Text).Col(L("an_this_period"), ColumnKind.Number)
            .Col(L("an_previous_period"), ColumnKind.Number).Col(L("an_change"), ColumnKind.Percent));
        void K(string key, Kpi v) => kpi.Row(L(key), v.Value, v.Previous, v.ChangePercent);
        K("an_revenue", k.Revenue); K("an_orders", k.Orders); K("report_avg", k.AverageCheck); K("an_guests", k.Guests); K("an_per_guest", k.AveragePerGuest);
        K("recipe_profit", k.Profit); K("recipe_margin", k.MarginPercent); K("shift_discounts", k.Discounts); K("delivery_fee", k.DeliveryFees);
        K("an_cancelled", k.Cancelled); K("an_cancelled_amount", k.CancelledAmount); K("an_waiter_earned", k.WaiterEarned);
        return list;
    }

    // ================= sales =================

    private async Task<List<Block>> SalesAsync(AnalyticsFilter f)
    {
        var s = await new AnalyticsService(_db).SalesAsync(f);
        var hours = s.Hours.SkipWhile(h => h.Orders == 0).Reverse().SkipWhile(h => h.Orders == 0).Reverse().ToList();
        return new List<Block>
        {
            new CardBlock(L("an_heatmap"), new HeatBlock(s.Heatmap, Weekdays, L("an_orders"))),
            new ColumnsBlock(new Block[]
            {
                new CardBlock(L("report_hours"), hours.Count == 0 ? new EmptyBlock() : new BarBlock(hours.Select(h => new Point(h.Hour.ToString("00"), h.Revenue, null,
                    h.Hour.ToString("00") + ":00\n" + Money(h.Revenue) + "\n" + L("an_orders") + ": " + h.Orders)).ToList())),
                new CardBlock(L("an_weekday_avg"), new BarBlock(s.Weekdays.Select(w => new Point(Weekdays[w.Weekday], w.AveragePerDay, null,
                    Weekdays[w.Weekday] + "\n" + Money(w.AveragePerDay) + " " + L("an_per_day") + "\n" + L("an_orders") + ": " + w.Orders)).ToList()))
            }),
            new CardBlock(L("report_daily"), new TableBlock(Keep(PeriodTable(L("report_daily"), s.Daily.Where(d => d.Orders > 0 || f.Days <= 31), false)))),
            s.Monthly.Count > 1 ? new CardBlock(L("an_monthly"), new TableBlock(Keep(PeriodTable(L("an_monthly"), s.Monthly, true)))) : new EmptyBlock()
        };
    }

    private ReportTable PeriodTable(string title, IEnumerable<PeriodRow> rows, bool months)
    {
        var t = new ReportTable(title).Col(months ? L("an_month") : L("an_day"), months ? ColumnKind.Text : ColumnKind.Date)
            .Col(L("an_orders"), ColumnKind.Integer).Col(L("an_guests"), ColumnKind.Integer).Col(L("an_revenue"), ColumnKind.Money)
            .Col(L("report_avg"), ColumnKind.Money).Col(L("shift_discounts"), ColumnKind.Money)
            .Col(L("btn_pay_cash"), ColumnKind.Money).Col(L("btn_pay_card"), ColumnKind.Money).Col(L("pay_transfer_short"), ColumnKind.Money)
            .Col(L("recipe_profit"), ColumnKind.Money);
        foreach (var r in rows)
            t.Row(months ? MonthName(r.Start) : r.Start.ToDateTime(TimeOnly.MinValue), r.Orders, r.Guests, r.Revenue, r.AverageCheck, r.Discounts, r.Cash, r.Card, r.Transfer, r.Profit);
        return t;
    }

    // ================= payments =================

    private async Task<List<Block>> PaymentsAsync(AnalyticsFilter f)
    {
        var p = await new AnalyticsService(_db).PaymentsAsync(f);
        var tiles = p.Methods.Select(m => new Tile(MethodName(m.Method), Money(m.Amount), Note: Fmt.Percent(m.Percent) + " · " + m.Payments + " " + L("an_payments_count"), Accent: m.Method == PaymentMethod.Cash)).ToList();
        tiles.Add(new Tile(L("an_split_bills"), Fmt.Int(p.SplitBills), Note: L("an_split_note")));
        var byMonth = p.Daily.Count > 62;
        var points = (byMonth ? p.Monthly : p.Daily).Select(d => new Point(byMonth ? MonthShort(d.Start) : d.Start.ToString("dd.MM"), d.Total, null,
            (byMonth ? MonthName(d.Start) : d.Start.ToString("dd.MM.yyyy")) + "\n" + Money(d.Total) + "\n" + L("btn_pay_cash") + ": " + Money(d.Cash)
            + "\n" + L("btn_pay_card") + ": " + Money(d.Card) + "\n" + L("pay_transfer_short") + ": " + Money(d.Transfer))).ToList();

        ReportTable Methods(string title, IEnumerable<PaymentPeriodRow> rows, bool months)
        {
            var t = new ReportTable(title).Col(months ? L("an_month") : L("an_day"), months ? ColumnKind.Text : ColumnKind.Date)
                .Col(L("btn_pay_cash"), ColumnKind.Money).Col(L("btn_pay_card"), ColumnKind.Money).Col(L("pay_transfer_short"), ColumnKind.Money).Col(L("an_total"), ColumnKind.Money);
            foreach (var r in rows) t.Row(months ? MonthName(r.Start) : r.Start.ToDateTime(TimeOnly.MinValue), r.Cash, r.Card, r.Transfer, r.Total);
            return t;
        }
        return new List<Block>
        {
            new TilesBlock(tiles),
            new CardBlock(L("an_payments_by_" + (byMonth ? "month" : "day")), new BarBlock(points)),
            new ColumnsBlock(new Block[]
            {
                new CardBlock(L("an_payments_by_day"), new TableBlock(Keep(Methods(L("an_payments_by_day"), p.Daily.Where(d => d.Total > 0 || f.Days <= 31), false)))),
                new CardBlock(L("an_monthly"), new TableBlock(Keep(Methods(L("an_monthly"), p.Monthly, true))))
            }),
            new CardBlock(L("an_shifts_cash"), new TableBlock(Keep(ShiftTable(L("an_shifts_cash"), p.Shifts))))
        };
    }

    private ReportTable ShiftTable(string title, IEnumerable<ShiftCashRow> rows)
    {
        var t = new ReportTable(title).Col("№", ColumnKind.Text).Col(L("an_opened"), ColumnKind.DateTime).Col(L("an_closed"), ColumnKind.DateTime)
            .Col(L("an_opened_by"), ColumnKind.Text).Col(L("an_revenue"), ColumnKind.Money).Col(L("btn_pay_cash"), ColumnKind.Money)
            .Col(L("an_expected_cash"), ColumnKind.Money).Col(L("an_counted_cash"), ColumnKind.Money).Col(L("an_difference"), ColumnKind.Money);
        foreach (var s in rows)
            t.Row(s.ShiftId.ToString(), Local(s.OpenedAtUtc), s.ClosedAtUtc is { } c ? Local(c) : null, s.OpenedBy, s.Sales, s.Cash, s.ExpectedCash, s.CountedCash, s.Difference);
        return t;
    }

    /// <summary>The restaurant's clock (Uzbekistan, UTC+5), wherever the website runs.</summary>
    public static DateTime Local(DateTime utc) => TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc, DateTimeKind.Utc), RestaurantTime.Zone);

    // ================= waiters =================

    private async Task<List<Block>> WaitersAsync(AnalyticsFilter f)
    {
        var w = await new AnalyticsService(_db).WaitersAsync(f);
        var t = new ReportTable(L("an_page_waiters")).Col(L("an_waiter"), ColumnKind.Text).Col(L("an_orders"), ColumnKind.Integer)
            .Col(L("an_revenue"), ColumnKind.Money).Col(L("report_avg"), ColumnKind.Money).Col(L("an_percent"), ColumnKind.Percent).Col(L("an_earned"), ColumnKind.Money)
            .Col(L("an_guests"), ColumnKind.Integer).Col(L("an_tables"), ColumnKind.Integer).Col(L("shift_discounts"), ColumnKind.Money)
            .Col(L("an_cancelled_short"), ColumnKind.Integer).Col(L("an_minutes_at_table"), ColumnKind.Integer);
        foreach (var x in w.Waiters)
            t.Row(x.Name, x.Orders, x.Revenue, x.AverageCheck, x.EffectivePercent, x.Earned, x.Guests, x.Tables, x.Discounts, x.Cancelled, (int)x.AverageServiceMinutes);
        return new List<Block>
        {
            new ColumnsBlock(new Block[]
            {
                new CardBlock(L("an_revenue"), new BarsBlock(w.Waiters.Select(x => (x.Name, x.Revenue, Money(x.Revenue))).ToList())),
                new CardBlock(L("report_avg"), new BarsBlock(w.Waiters.Where(x => x.Orders > 0).OrderByDescending(x => x.AverageCheck).Select(x => (x.Name, x.AverageCheck, Money(x.AverageCheck))).ToList()))
            }),
            new CardBlock(L("an_page_waiters"), new TableBlock(Keep(t), "waiter", w.Waiters.Select(x => x.WaiterId).ToList()), L("an_pick_row"))
        };
    }

    /// <summary>The table-by-table card for one waiter (opened from the waiters or payroll table).</summary>
    public async Task<Block> WaiterDetailAsync(AnalyticsFilter f, int waiterId, DateOnly? month)
    {
        var a = new AnalyticsService(_db);
        string name;
        List<WaiterTableRow> rows;
        if (month is { } m)
        {
            var payroll = await a.PayrollAsync(m.Year, m.Month);
            var row = payroll.Rows.FirstOrDefault(r => r.WaiterId == waiterId);
            name = row?.Name ?? "?";
            rows = row?.Tables.ToList() ?? new();
        }
        else
        {
            rows = await a.WaiterTablesAsync(f, waiterId);
            name = await _db.Users.Where(u => u.Id == waiterId).Select(u => u.FullName).FirstOrDefaultAsync() ?? "?";
        }
        return new CardBlock(name + " — " + L("an_by_table"), new TableBlock(WaiterTableTable(L("an_by_table"), rows)));
    }

    private ReportTable WaiterTableTable(string title, IEnumerable<WaiterTableRow> rows)
    {
        var t = new ReportTable(title).Col(L("an_hall"), ColumnKind.Text).Col(L("an_table"), ColumnKind.Text).Col(L("an_orders"), ColumnKind.Integer)
            .Col(L("an_food_paid"), ColumnKind.Money).Col(L("an_percent"), ColumnKind.Percent).Col(L("an_earned"), ColumnKind.Money);
        foreach (var r in rows) t.Row(r.TableId is null ? L("an_no_table") : r.Hall, r.Table, r.Orders, r.FoodPaid, r.Percent, r.Earned);
        return t;
    }

    // ================= payroll =================

    private async Task<List<Block>> PayrollAsync(DateOnly month)
    {
        var page = await new AnalyticsService(_db).PayrollAsync(month.Year, month.Month);
        var t = new ReportTable(L("an_page_payroll") + " " + MonthName(month)).Col(L("an_waiter"), ColumnKind.Text).Col(L("an_orders"), ColumnKind.Integer)
            .Col(L("an_food_paid"), ColumnKind.Money).Col(L("an_percent"), ColumnKind.Percent).Col(L("an_earned"), ColumnKind.Money);
        foreach (var r in page.Rows) t.Row(r.Name, r.Orders, r.FoodPaid, r.FoodPaid == 0 ? 0 : Math.Round(r.Earned / r.FoodPaid * 100, 2), r.Earned);
        var all = new ReportTable(L("an_by_table")).Col(L("an_waiter"), ColumnKind.Text).Col(L("an_hall"), ColumnKind.Text).Col(L("an_table"), ColumnKind.Text)
            .Col(L("an_orders"), ColumnKind.Integer).Col(L("an_food_paid"), ColumnKind.Money).Col(L("an_percent"), ColumnKind.Percent).Col(L("an_earned"), ColumnKind.Money);
        foreach (var r in page.Rows)
            foreach (var x in r.Tables) all.Row(r.Name, x.TableId is null ? L("an_no_table") : x.Hall, x.Table, x.Orders, x.FoodPaid, x.Percent, x.Earned);
        Keep(t);
        Keep(all);
        return new List<Block>
        {
            new MonthNavBlock(month, MonthName(month), L("an_payroll_note")),
            new TilesBlock(new[]
            {
                new Tile(L("an_payroll_total"), Money(page.TotalEarned), Accent: true, Note: MonthName(month)),
                new Tile(L("an_page_waiters"), Fmt.Int(page.Rows.Count), Note: L("an_with_sales")),
                new Tile(L("an_orders"), Fmt.Int(page.Rows.Sum(r => r.Orders)), Note: L("an_food_paid") + ": " + Money(page.Rows.Sum(r => r.FoodPaid)))
            }),
            new CardBlock(L("an_page_payroll"), new TableBlock(t, "payroll", page.Rows.Select(r => r.WaiterId).ToList()), L("an_pick_row"))
        };
    }

    // ================= tables =================

    private async Task<List<Block>> TablesAsync(AnalyticsFilter f)
    {
        var p = await new AnalyticsService(_db).TablesAsync(f);
        var halls = new ReportTable(L("an_halls")).Col(L("an_hall"), ColumnKind.Text).Col(L("an_tables"), ColumnKind.Integer)
            .Col(L("an_orders"), ColumnKind.Integer).Col(L("an_revenue"), ColumnKind.Money).Col(L("report_avg"), ColumnKind.Money);
        foreach (var h in p.Halls) halls.Row(h.Hall, h.Tables, h.Orders, h.Revenue, h.AverageCheck);
        var t = new ReportTable(L("nav_tables")).Col(L("an_hall"), ColumnKind.Text).Col(L("an_table"), ColumnKind.Text).Col(L("f_seats"), ColumnKind.Integer)
            .Col(L("an_orders"), ColumnKind.Integer).Col(L("an_guests"), ColumnKind.Integer).Col(L("an_revenue"), ColumnKind.Money)
            .Col(L("report_avg"), ColumnKind.Money).Col(L("an_minutes_at_table"), ColumnKind.Integer).Col(L("an_orders_per_day"), ColumnKind.Number)
            .Col(L("an_revenue_per_seat"), ColumnKind.Money);
        foreach (var x in p.Tables) t.Row(x.Hall, x.Table, x.Seats, x.Orders, x.Guests, x.Revenue, x.AverageCheck, (int)x.AverageMinutes, x.OrdersPerDay, x.RevenuePerSeat);
        return new List<Block>
        {
            new ColumnsBlock(new Block[]
            {
                new CardBlock(L("an_halls"), new TableBlock(Keep(halls))),
                new CardBlock(L("an_top_tables"), new BarsBlock(p.Tables.Where(x => x.Orders > 0).Take(8).Select(x => (x.Hall + " · " + x.Table, x.Revenue, Money(x.Revenue))).ToList()))
            }),
            new CardBlock(L("nav_tables"), new TableBlock(Keep(t)))
        };
    }

    // ================= products =================

    private async Task<List<Block>> ProductsAsync(AnalyticsFilter f)
    {
        var p = await new AnalyticsService(_db).ProductsAsync(f);
        var t = new ReportTable(L("report_dishes")).Col(L("order_dish"), ColumnKind.Text).Col(L("an_category"), ColumnKind.Text)
            .Col(L("order_qty"), ColumnKind.Integer).Col(L("an_revenue"), ColumnKind.Money).Col(L("an_share"), ColumnKind.Percent).Col(L("an_abc_revenue"), ColumnKind.Text)
            .Col(L("shift_cogs"), ColumnKind.Money).Col(L("recipe_profit"), ColumnKind.Money).Col(L("recipe_margin"), ColumnKind.Percent).Col(L("an_abc_profit"), ColumnKind.Text)
            .Col(L("an_prep_short"), ColumnKind.Number);
        foreach (var d in p.Dishes)
            t.Row(Pick(d.NameUz, d.NameRu), Pick(d.CategoryUz, d.CategoryRu), d.Quantity, d.Revenue, d.SharePercent, d.ByRevenue.ToString(),
                d.Cost, d.Profit, d.MarginPercent, d.ByProfit.ToString(), d.AveragePrepMinutes);
        var notSold = Keep(new ReportTable(L("an_not_sold")).Col(L("order_dish"), ColumnKind.Text));
        foreach (var d in p.NotSold) notSold.Row(Pick(d.NameUz, d.NameRu));
        return new List<Block>
        {
            new TilesBlock(new[]
            {
                new Tile(L("an_dishes_sold"), Fmt.Int(p.Dishes.Sum(d => d.Quantity)), Note: p.Dishes.Count + " " + L("an_kinds")),
                new Tile(L("an_abc_a"), Fmt.Int(p.Dishes.Count(d => d.ByProfit == AbcClass.A)), Note: L("an_abc_by_profit")),
                new Tile(L("an_not_sold"), Fmt.Int(p.NotSold.Count), Note: L("an_not_sold_note")),
                new Tile(L("an_prep_time"), p.AveragePrepMinutes is { } m ? m.ToString("0.#", Fmt.Culture) + " " + L("kitchen_min") : "—", Note: L("an_prep_note"))
            }),
            new ColumnsBlock(new Block[]
            {
                new CardBlock(L("an_categories"), new SharesBlock(p.Categories.Select(c => (Pick(c.NameUz, c.NameRu), c.Revenue, c.SharePercent)).ToList())),
                new CardBlock(L("an_top_profit"), new BarsBlock(p.Dishes.OrderByDescending(d => d.Profit).Take(8).Select(d => (Pick(d.NameUz, d.NameRu), d.Profit, Money(d.Profit))).ToList()))
            }),
            new CardBlock(L("report_dishes"), new TableBlock(Keep(t)), L("an_abc_note")),
            new CardBlock(L("an_not_sold"), p.NotSold.Count == 0 ? new EmptyBlock() : new ChipsBlock(p.NotSold.Select(d => Pick(d.NameUz, d.NameRu)).ToList()))
        };
    }

    // ================= customers =================

    private async Task<List<Block>> CustomersAsync(AnalyticsFilter f)
    {
        var c = await new AnalyticsService(_db).CustomersAsync(f);
        var t = new ReportTable(L("an_top_customers")).Col(L("an_customer"), ColumnKind.Text).Col(L("an_phone"), ColumnKind.Text)
            .Col(L("an_orders"), ColumnKind.Integer).Col(L("an_revenue"), ColumnKind.Money).Col(L("report_avg"), ColumnKind.Money)
            .Col(L("an_last_order"), ColumnKind.DateTime).Col(L("an_new"), ColumnKind.Text);
        foreach (var r in c.Top) t.Row(r.Name, PhoneHelper.Format(r.Phone), r.Orders, r.Revenue, r.AverageCheck, Local(r.LastOrderUtc), r.IsNew ? "✓" : "");
        var couriers = new ReportTable(L("an_couriers")).Col(L("an_courier"), ColumnKind.Text).Col(L("an_orders"), ColumnKind.Integer)
            .Col(L("an_revenue"), ColumnKind.Money).Col(L("delivery_fee"), ColumnKind.Money);
        foreach (var r in c.Couriers) couriers.Row(r.CourierId is null ? L("an_no_courier") : r.Name, r.Orders, r.Revenue, r.DeliveryFees);
        return new List<Block>
        {
            new TilesBlock(new[]
            {
                new Tile(L("an_customers"), Fmt.Int(c.Customers), Note: L("an_with_phone")),
                new Tile(L("an_new_customers"), Fmt.Int(c.NewCustomers), Note: L("an_first_order")),
                new Tile(L("an_returning"), Fmt.Int(c.ReturningCustomers), Note: L("an_ordered_before")),
                new Tile(L("an_delivery_orders"), Fmt.Int(c.DeliveryOrders), Note: Money(c.DeliveryRevenue)),
                new Tile(L("an_delivery_avg"), Money(c.DeliveryAverageCheck))
            }),
            new CardBlock(L("an_top_customers"), new TableBlock(Keep(t))),
            new CardBlock(L("an_couriers"), new TableBlock(Keep(couriers)))
        };
    }

    // ================= control =================

    private async Task<List<Block>> ControlAsync(AnalyticsFilter f)
    {
        var c = await new AnalyticsService(_db).ControlAsync(f);
        var t = new ReportTable(L("an_cancelled_orders")).Col("№", ColumnKind.Text).Col(L("an_time"), ColumnKind.DateTime).Col(L("an_table"), ColumnKind.Text)
            .Col(L("an_waiter"), ColumnKind.Text).Col(L("an_cancelled_by"), ColumnKind.Text).Col(L("an_reason"), ColumnKind.Text)
            .Col(L("an_amount"), ColumnKind.Money).Col(L("an_after_kitchen"), ColumnKind.Text);
        foreach (var r in c.Cancelled)
            t.Row(r.OrderId.ToString(), Local(r.CancelledAtUtc), r.Table, r.Waiter, r.CancelledBy ?? "—", r.Reason ?? "—", r.Amount, r.WasSentToKitchen ? "✓" : "");
        var discounts = new ReportTable(L("an_discounts_by_waiter")).Col(L("an_waiter"), ColumnKind.Text).Col(L("an_orders"), ColumnKind.Integer).Col(L("shift_discounts"), ColumnKind.Money);
        foreach (var r in c.Discounts) discounts.Row(r.Waiter, r.Orders, r.Discounts);
        var removed = new ReportTable(L("an_removed_dishes")).Col(L("an_time"), ColumnKind.DateTime).Col("№", ColumnKind.Text)
            .Col(L("order_dish"), ColumnKind.Text).Col(L("order_qty"), ColumnKind.Integer);
        foreach (var r in c.RemovedDishes) removed.Row(Local(r.CreatedAtUtc), r.OrderId.ToString(), Pick(r.NameUz, r.NameRu), r.Quantity);
        return new List<Block>
        {
            new TilesBlock(new[]
            {
                new Tile(L("an_cancelled"), Fmt.Int(c.Cancelled.Count), Note: Money(c.Cancelled.Sum(x => x.Amount))),
                new Tile(L("an_cancelled_after_kitchen"), Fmt.Int(c.Cancelled.Count(x => x.WasSentToKitchen)), Note: L("an_food_wasted")),
                new Tile(L("shift_discounts"), Money(c.Discounts.Sum(x => x.Discounts)), Note: c.Discounts.Sum(x => x.Orders) + " " + L("an_orders_lower")),
                new Tile(L("an_removed_dishes"), Fmt.Int(c.RemovedDishes.Sum(x => x.Quantity)), Note: L("an_removed_note")),
                new Tile(L("an_cash_differences"), Money(c.ShiftDifferences.Sum(x => x.Difference ?? 0)), Note: c.ShiftDifferences.Count + " " + L("an_shifts_lower"))
            }),
            new CardBlock(L("an_cancelled_orders"), new TableBlock(Keep(t))),
            new ColumnsBlock(new Block[]
            {
                new CardBlock(L("an_discounts_by_waiter"), new TableBlock(Keep(discounts))),
                new CardBlock(L("an_removed_dishes"), new TableBlock(Keep(removed)))
            }),
            new CardBlock(L("an_cash_differences"), new TableBlock(Keep(ShiftTable(L("an_cash_differences"), c.ShiftDifferences))))
        };
    }

    // ================= stock =================

    private async Task<List<Block>> StockAsync(AnalyticsFilter f)
    {
        var r = await new ReportService(_db).BuildAsync(f.From, f.To);
        var t = new ReportTable(L("nav_stock")).Col(L("recipe_ingredient"), ColumnKind.Text).Col(L("stock_onhand"), ColumnKind.Text)
            .Col(L("stock_min"), ColumnKind.Text).Col(L("an_value"), ColumnKind.Money).Col(L("stock_low"), ColumnKind.Text);
        foreach (var s in r.Stock.OrderByDescending(s => s.IsLow).ThenBy(s => s.Name))
            t.Row(s.Name, UnitHelper.Format(s.OnHand, s.Unit), UnitHelper.Format(s.Min, s.Unit), Math.Round(s.Value, 0), s.IsLow ? "!" : "");
        return new List<Block>
        {
            new TilesBlock(new[]
            {
                new Tile(L("report_stock_value"), Money(r.StockValue), Accent: true, Note: L("an_now")),
                new Tile(L("stock_low"), Fmt.Int(r.Stock.Count(s => s.IsLow)), Note: L("an_low_note")),
                new Tile(L("op_waste"), Money(r.WasteCost), Note: L("an_in_period"))
            }),
            new CardBlock(L("nav_stock"), new TableBlock(Keep(t)))
        };
    }
}

/// <summary>The restaurants are in Uzbekistan: days and hours are counted in Tashkent time, wherever the server is.</summary>
public static class RestaurantTime
{
    public static readonly TimeZoneInfo Zone = Find();

    private static TimeZoneInfo Find()
    {
        foreach (var id in new[] { "Asia/Tashkent", "West Asia Standard Time" })
            try { return TimeZoneInfo.FindSystemTimeZoneById(id); } catch (TimeZoneNotFoundException) { }
        return TimeZoneInfo.CreateCustomTimeZone("UZT", TimeSpan.FromHours(5), "Tashkent", "Tashkent");
    }

    public static DateOnly Today => DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, Zone));
}
