using Microsoft.EntityFrameworkCore;
using SwedPos.Data;
using SwedPos.Domain;
using SwedPos.Services;

namespace SwedPos.Cloud.Services;

/// <summary>
/// 60 days of a made-up Samarkand restaurant, built with the desktop's own services (orders, payments, waiter
/// percent, cancellations, deliveries), so the demo shows exactly what a real restaurant would see.
/// </summary>
public static class DemoData
{
    public static async Task SeedAsync(SwedPosDbContext db, int seed = 42)
    {
        var rnd = new Random(seed);
        await DbSeeder.SeedRolesAsync(db);
        var roles = await db.Roles.ToDictionaryAsync(r => r.Name);
        var auth = new AuthService(db);
        var owner = await auth.CreateUserAsync("Owner", "1000", roles["Owner"].Id);
        var waiters = new List<User>();
        foreach (var (name, pin, pct) in new[] { ("Aziz Karimov", "1001", 5m), ("Bekzod Rahimov", "1002", 4m), ("Dilnoza Yusupova", "1003", 5m), ("Jasur Toshev", "1004", 3m) })
        {
            var u = await auth.CreateUserAsync(name, pin, roles["Waiter"].Id);
            await new UserService(db).SetWaiterPercentAsync(u.Id, pct);
            waiters.Add(u);
        }
        var courier = await auth.CreateUserAsync("Sardor (kuryer)", "1005", roles["Courier"].Id);
        var operatorUser = await auth.CreateUserAsync("Malika (operator)", "1006", roles["CallCenter"].Id);

        var menu = new MenuService(db);
        var stock = new StockService(db);
        var cats = new Dictionary<string, int>();
        foreach (var (uz, ru) in new[] { ("Milliy taomlar", "Национальные блюда"), ("Salatlar", "Салаты"), ("Ichimliklar", "Напитки"), ("Shirinliklar", "Десерты") })
            cats[uz] = (await menu.SaveCategoryAsync(0, uz, ru)).Id;
        var meat = await stock.SaveIngredientAsync(0, "Mol go'shti", Unit.Gram, 5000, null);
        await stock.ReceiveAsync(meat.Id, 900_000, 900_000 * 110m, null, null);
        var rice = await stock.SaveIngredientAsync(0, "Guruch", Unit.Gram, 5000, null);
        await stock.ReceiveAsync(rice.Id, 600_000, 600_000 * 18m, null, null);
        var veg = await stock.SaveIngredientAsync(0, "Sabzavotlar", Unit.Gram, 3000, null);
        await stock.ReceiveAsync(veg.Id, 400_000, 400_000 * 12m, null, null);

        var dishes = new List<(int Id, int Weight)>();
        async Task Dish(string cat, string uz, string ru, decimal price, int weight, int meatG = 0, int riceG = 0, int vegG = 0)
        {
            var d = await menu.SaveDishAsync(0, cats[cat], uz, ru, price, null, true);
            if (meatG > 0) await stock.SetRecipeLineAsync(d.Id, meat.Id, meatG);
            if (riceG > 0) await stock.SetRecipeLineAsync(d.Id, rice.Id, riceG);
            if (vegG > 0) await stock.SetRecipeLineAsync(d.Id, veg.Id, vegG);
            dishes.Add((d.Id, weight));
        }
        await Dish("Milliy taomlar", "Samarqand oshi", "Самаркандский плов", 55_000, 30, 120, 200, 80);
        await Dish("Milliy taomlar", "Shashlik (mol)", "Шашлык (говядина)", 32_000, 26, 180);
        await Dish("Milliy taomlar", "Lag'mon", "Лагман", 38_000, 16, 90, 0, 120);
        await Dish("Milliy taomlar", "Manti", "Манты", 36_000, 14, 110, 0, 40);
        await Dish("Milliy taomlar", "Qozon kabob", "Казан-кабоб", 75_000, 8, 300, 0, 150);
        await Dish("Milliy taomlar", "Mastava", "Мастава", 30_000, 7, 60, 60, 80);
        await Dish("Salatlar", "Achchiq-chuchuk", "Ачичук", 15_000, 20, 0, 0, 200);
        await Dish("Salatlar", "Olivye", "Оливье", 25_000, 9, 40, 0, 150);
        await Dish("Salatlar", "Sezar", "Цезарь", 42_000, 6, 60, 0, 160);
        await Dish("Ichimliklar", "Ko'k choy (choynak)", "Зелёный чай (чайник)", 8_000, 34);
        await Dish("Ichimliklar", "Limonli choy", "Чай с лимоном", 15_000, 10);
        await Dish("Ichimliklar", "Kompot", "Компот", 18_000, 12);
        await Dish("Ichimliklar", "Coca-Cola 1 l", "Coca-Cola 1 л", 16_000, 10);
        await Dish("Shirinliklar", "Navvot va pishiriqlar", "Нават и выпечка", 20_000, 6);
        await Dish("Shirinliklar", "Medovik", "Медовик", 28_000, 4);
        await Dish("Shirinliklar", "Pahlava", "Пахлава", 30_000, 0);

        var floor = new FloorService(db);
        var tables = new List<int>();
        foreach (var (hall, count, seats, pct) in new[] { ("Asosiy zal", 10, 4, (decimal?)null), ("VIP", 3, 8, 8m), ("Terrasa", 5, 4, (decimal?)null) })
        {
            var h = await floor.SaveHallAsync(0, hall);
            if (pct is { } p) await floor.SetHallPercentAsync(h.Id, p);
            for (var i = 1; i <= count; i++) tables.Add((await floor.SaveTableAsync(0, h.Id, (hall == "VIP" ? "V" : hall == "Terrasa" ? "T" : "") + i, seats)).Id);
        }

        var customers = new List<Customer>();
        var cs = new CustomerService(db);
        foreach (var (phone, name) in new[] { ("+998901234567", "Akmal"), ("+998935551122", "Gulnora"), ("+998977003344", "Shoxrux"), ("+998881112233", "Nodira"), ("+998901119988", "Rustam"), ("+998939876543", "Madina") })
            customers.Add(await cs.SaveAsync(phone, name, "Samarqand, Registon ko'chasi " + rnd.Next(1, 90)));

        var shifts = new ShiftService(db);
        await shifts.OpenAsync(owner, 300_000);
        var orders = new OrderService(db);
        var reasons = Texts.Get("uz", "cancel_reasons").Split('|');
        var now = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, Reports.RestaurantTime.Zone);
        var today = now.Date;
        var total = dishes.Sum(d => d.Weight);
        int PickDish() { var r = rnd.Next(total); foreach (var d in dishes) { if (r < d.Weight) return d.Id; r -= d.Weight; } return dishes[0].Id; }
        int[] hours = { 11, 12, 12, 13, 13, 13, 14, 14, 15, 16, 17, 18, 18, 19, 19, 19, 20, 20, 20, 21, 21, 22 };

        for (var day = 59; day >= 0; day--)
        {
            var date = today.AddDays(-day);
            var weekend = date.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday;
            var count = (weekend ? 34 : 22) + rnd.Next(0, 9) + (59 - day) / 8;
            if (day == 0) count = 14;
            for (var n = 0; n < count; n++)
            {
                var tableId = tables[rnd.Next(tables.Count)];
                var waiter = waiters[rnd.Next(waiters.Count)];
                Order order = null!;
                for (var i = 0; i < rnd.Next(2, 7); i++) order = await orders.AddDishAsync(tableId, waiter.Id, PickDish());
                await orders.SetGuestsAsync(order.Id, rnd.Next(1, 7));
                if (rnd.NextDouble() < 0.12) await orders.SetDiscountAsync(order.Id, rnd.NextDouble() < 0.7 ? 10 : 15);
                await orders.SendToKitchenAsync(order.Id);

                var at = date.AddHours(hours[rnd.Next(hours.Length)]).AddMinutes(rnd.Next(0, 60));
                if (day == 0 && at > now) at = now.AddMinutes(-rnd.Next(5, 300));

                if (rnd.NextDouble() < 0.025)
                {
                    await orders.CancelAsync(order.Id, true, "uz", waiter.Id, reasons[rnd.Next(reasons.Length)]);
                    Move(db, order.Id, at, rnd.Next(10, 40), cancelled: true);
                    continue;
                }
                var full = (await db.Orders.Include(o => o.Lines).FirstAsync(o => o.Id == order.Id)).Total;
                var r = rnd.NextDouble();
                if (r < 0.48) await orders.PayAsync(order.Id, PaymentMethod.Cash);
                else if (r < 0.78) await orders.PayAsync(order.Id, PaymentMethod.Card);
                else if (r < 0.94) await orders.PayAsync(order.Id, PaymentMethod.Transfer);
                else
                {
                    var cash = Math.Round(full * 0.6m / 1000) * 1000;
                    await orders.PayAsync(order.Id, new[] { new PaymentPart(PaymentMethod.Cash, cash), new PaymentPart(PaymentMethod.Card, full - cash) });
                }
                Move(db, order.Id, at, rnd.Next(35, 110), cancelled: false, prepMinutes: rnd.Next(8, 28));
            }
            for (var n = 0; n < rnd.Next(2, 6); n++)
            {
                var c = customers[rnd.Next(customers.Count)];
                var o = await orders.CreateRemoteOrderAsync(operatorUser.Id, OrderType.Delivery, c.Id, c.Address, 15_000);
                for (var i = 0; i < rnd.Next(1, 4); i++) await orders.AddDishToOrderAsync(o.Id, PickDish());
                (await db.Orders.FirstAsync(x => x.Id == o.Id)).CourierId = courier.Id;
                await db.SaveChangesAsync();
                await orders.PayAsync(o.Id, rnd.NextDouble() < 0.5 ? PaymentMethod.Cash : PaymentMethod.Transfer);
                var when = date.AddHours(hours[rnd.Next(hours.Length)]);
                if (day == 0 && when > now) when = now.AddMinutes(-30);
                Move(db, o.Id, when, rnd.Next(40, 70), cancelled: false);
            }
            db.ChangeTracker.Clear();   // keeps building fast: nothing from earlier days is needed
        }
        var open = await shifts.GetOpenAsync();
        var report = await shifts.BuildReportAsync(open!.Id);
        await shifts.CloseAsync(owner, report.ExpectedCash - 25_000, "Demo");
        await shifts.OpenAsync(owner, 300_000);
    }

    /// <summary>Moves an order to a moment in restaurant (Tashkent) time.</summary>
    private static void Move(SwedPosDbContext db, int orderId, DateTime restaurantLocal, int minutes, bool cancelled, int prepMinutes = 15)
    {
        var o = db.Orders.Include(x => x.Lines).Include(x => x.Payments).First(x => x.Id == orderId);
        var utc = TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(restaurantLocal, DateTimeKind.Unspecified), Reports.RestaurantTime.Zone);
        o.CreatedAt = utc.AddMinutes(-minutes);
        if (cancelled) o.CancelledAt = utc; else o.PaidAt = utc;
        foreach (var p in o.Payments) p.CreatedAt = utc;
        foreach (var l in o.Lines)
        {
            l.SentAt = o.CreatedAt.AddMinutes(3);
            if (!cancelled) l.ReadyAt = l.SentAt.Value.AddMinutes(prepMinutes);
        }
        foreach (var n in db.KitchenNotices.Where(n => n.OrderId == orderId)) n.CreatedAt = utc;
        db.SaveChanges();
    }
}
