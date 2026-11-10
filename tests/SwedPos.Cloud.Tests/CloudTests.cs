using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using SwedPos.Cloud;
using SwedPos.Cloud.Data;
using SwedPos.Cloud.Reports;
using SwedPos.Cloud.Services;
using SwedPos.Data;
using SwedPos.Domain;
using SwedPos.Services;

namespace SwedPos.Cloud.Tests;

/// <summary>Accounts, sync keys, receiving a restaurant's data and building every page, with in-memory databases.</summary>
public class CloudTests
{
    private sealed record Cloud(CloudDbContext Db, DemoTenants Tenants, CloudAccounts Accounts, SyncReceiver Receiver);

    private static Cloud NewCloud()
    {
        var root = new InMemoryDatabaseRoot();
        var db = new CloudDbContext(new DbContextOptionsBuilder<CloudDbContext>().UseInMemoryDatabase("control", root).Options);
        var tenants = new DemoTenants(root);
        return new Cloud(db, tenants, new CloudAccounts(db, tenants), new SyncReceiver(db, tenants));
    }

    [Theory]
    [InlineData("+998 90 123-45-67", "998901234567")]
    [InlineData("901234567", "998901234567")]
    [InlineData("12345", null)]
    public void Phone_numbers_are_stored_as_digits_with_the_country_code(string input, string? expected) =>
        Assert.Equal(expected, Phone.Normalize(input));

    [Fact]
    public async Task An_owner_logs_in_with_phone_and_password_and_sees_only_their_restaurants()
    {
        var c = NewCloud();
        var (a, _) = await c.Accounts.AddRestaurantAsync("Marokand");
        var (b, _) = await c.Accounts.AddRestaurantAsync("Other");
        await c.Accounts.SaveAccountAsync("+998 90 111 22 33", "Owner", "secret-pass", false, new[] { a.Id });
        await c.Accounts.SaveAccountAsync("998901112244", "Staff", "admin-pass1", true, Array.Empty<int>());

        Assert.Null(await c.Accounts.LoginAsync("998901112233", "wrong-pass"));
        Assert.Null(await c.Accounts.LoginAsync("998900000000", "secret-pass"));
        var owner = await c.Accounts.LoginAsync("90 111 22 33", "secret-pass");
        Assert.NotNull(owner);
        Assert.Equal(new[] { "Marokand" }, (await c.Accounts.RestaurantsForAsync(owner!.Id)).Select(r => r.Name));

        var admin = await c.Accounts.LoginAsync("998901112244", "admin-pass1");
        Assert.Equal(2, (await c.Accounts.RestaurantsForAsync(admin!.Id)).Count);
        await Assert.ThrowsAsync<ValidationException>(() => c.Accounts.SaveAccountAsync("998901112255", "X", "short", false, new[] { b.Id }));
    }

    [Fact]
    public async Task Only_the_current_sync_key_is_accepted_and_it_is_stored_as_a_hash()
    {
        var c = NewCloud();
        var (r, key) = await c.Accounts.AddRestaurantAsync("Marokand");

        Assert.DoesNotContain(key, r.KeyHash);
        Assert.Equal(r.Id, (await c.Receiver.FindAsync(key))?.Id);
        Assert.Null(await c.Receiver.FindAsync("spk_wrong"));

        var renewed = await c.Accounts.RenewKeyAsync(r.Id);
        Assert.Null(await c.Receiver.FindAsync(key));
        Assert.Equal(r.Id, (await c.Receiver.FindAsync(renewed))?.Id);
    }

    [Fact]
    public async Task A_restaurant_batch_is_stored_and_every_page_builds_in_both_languages()
    {
        var c = NewCloud();
        var (cloudRestaurant, _) = await c.Accounts.AddRestaurantAsync("Marokand");

        // A small restaurant with a few paid orders, sent like the server PC does.
        var shop = new SwedPosDbContext(new DbContextOptionsBuilder<SwedPosDbContext>().UseInMemoryDatabase(Guid.NewGuid().ToString()).Options);
        await DbSeeder.SeedRolesAsync(shop);
        var waiter = await new AuthService(shop).CreateUserAsync("Aziz", "1111", (await shop.Roles.SingleAsync(x => x.Name == "Cashier")).Id);
        await new UserService(shop).SetWaiterPercentAsync(waiter.Id, 5);
        var cat = await new MenuService(shop).SaveCategoryAsync(0, "Taomlar", "Блюда");
        var osh = await new MenuService(shop).SaveDishAsync(0, cat.Id, "Osh", "Плов", 45000, null, true);
        var hall = await new FloorService(shop).SaveHallAsync(0, "Main");
        var table = await new FloorService(shop).SaveTableAsync(0, hall.Id, "1", 4);
        await new ShiftService(shop).OpenAsync(waiter, 0);
        var orders = new OrderService(shop);
        for (var i = 0; i < 3; i++)
        {
            var o = await orders.AddDishAsync(table.Id, waiter.Id, osh.Id);
            await orders.PayAsync(o.Id, i == 0 ? PaymentMethod.Card : PaymentMethod.Cash);
        }
        var batch = await new CloudSyncBuilder(shop).BuildAsync(new SyncCursor(), DateTime.UtcNow, "1.3.0");

        await c.Receiver.ReceiveAsync(cloudRestaurant, batch);

        Assert.Equal("1.3.0", (await c.Db.Restaurants.FindAsync(cloudRestaurant.Id))!.LastAppVersion);
        await using var tenant = c.Tenants.Open(cloudRestaurant.Id);
        Assert.Equal(3, await tenant.Orders.CountAsync());

        var today = DateOnly.FromDateTime(DateTime.Today);
        var filter = new AnalyticsFilter(today.AddDays(-6), today);
        foreach (var lang in new[] { "uz", "ru" })
            foreach (var page in ReportBuilder.Pages)
            {
                var built = await new ReportBuilder(tenant, lang).BuildAsync(page, filter, new DateOnly(today.Year, today.Month, 1));
                Assert.NotEmpty(built.Blocks);
                Assert.NotEmpty(built.Tables);
            }

        var overview = await new AnalyticsService(tenant).OverviewAsync(filter);
        Assert.Equal(135_000, overview.Kpis.Revenue.Value);
        Assert.Equal(6_750, overview.Kpis.WaiterEarned.Value);
    }

    [Fact]
    public void The_language_switch_never_redirects_to_another_site()
    {
        Assert.Equal("/uz/r/1/sales", ChartMath.SafeLocal("/uz/r/1/sales"));
        Assert.Equal("/", ChartMath.SafeLocal("//evil.example"));
        Assert.Equal("/", ChartMath.SafeLocal("https://evil.example"));
        Assert.Equal("/", ChartMath.SafeLocal("/\\evil.example"));
    }

    [Fact]
    public void Every_page_and_text_used_by_the_website_exists_in_both_languages()
    {
        foreach (var page in ReportBuilder.Pages)
            foreach (var lang in new[] { "uz", "ru" })
            {
                Assert.NotEqual("an_page_" + page, Texts.Get(lang, "an_page_" + page));
                Assert.NotEqual("an_hint_" + page, Texts.Get(lang, "an_hint_" + page));
            }
        Assert.NotEqual(Texts.Get("uz", "web_login"), Texts.Get("ru", "web_login"));
    }
}
