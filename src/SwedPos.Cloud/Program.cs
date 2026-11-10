using System.Security.Claims;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.EntityFrameworkCore;
using SwedPos.Cloud;
using SwedPos.Cloud.Components;
using SwedPos.Cloud.Data;
using SwedPos.Cloud.Reports;
using SwedPos.Cloud.Services;
using SwedPos.Domain;
using SwedPos.Services;

var builder = WebApplication.CreateBuilder(args);

// Control database (restaurants, accounts) and the PostgreSQL server where each restaurant gets its own database.
// Without a database the site runs in demo mode on made-up data (for trying it out and for sales demos).
var control = builder.Configuration.GetConnectionString("Control");
var demo = string.IsNullOrWhiteSpace(control);
if (demo)
{
    var root = new Microsoft.EntityFrameworkCore.Storage.InMemoryDatabaseRoot();
    builder.Services.AddDbContext<CloudDbContext>(o => o.UseInMemoryDatabase("control", root));
    builder.Services.AddSingleton<TenantDatabases>(new DemoTenants(root));
    builder.Services.AddSingleton(new DemoMode(true, "+998 90 000 00 00", "demo12345"));
}
else
{
    var server = builder.Configuration.GetConnectionString("Server") ?? control!;
    builder.Services.AddDbContext<CloudDbContext>(o => o.UseNpgsql(control));
    builder.Services.AddSingleton(new TenantDatabases(server));
    builder.Services.AddSingleton(new DemoMode(false));
}
builder.Services.AddScoped<CloudAccounts>();
builder.Services.AddScoped<SyncReceiver>();

builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(o =>
    {
        o.LoginPath = "/uz/login";
        o.ExpireTimeSpan = TimeSpan.FromDays(30);
        o.SlidingExpiration = true;
        o.Cookie.Name = "swedpos.auth";
        o.Cookie.HttpOnly = true;
        o.Cookie.SameSite = SameSiteMode.Lax;
        o.Cookie.SecurePolicy = CookieSecurePolicy.SameAsRequest;
    });
builder.Services.AddAuthorization();
builder.Services.AddCascadingAuthenticationState();
builder.Services.AddHttpContextAccessor();
builder.Services.AddRazorComponents().AddInteractiveServerComponents();
builder.WebHost.ConfigureKestrel(k => k.Limits.MaxRequestBodySize = 64 * 1024 * 1024);   // a first sync can be large

var app = builder.Build();

// Admin commands: dotnet run -- add-restaurant "Name" | add-account phone "Name" password restaurantId[,id] [admin] | renew-key id | list
if (!demo && args.Length > 0 && await AdminCommands.RunAsync(app, args)) return;

using (var scope = app.Services.CreateScope())
{
    var controlDb = scope.ServiceProvider.GetRequiredService<CloudDbContext>();
    if (!demo) await controlDb.Database.MigrateAsync();
    else
    {
        var accounts = scope.ServiceProvider.GetRequiredService<CloudAccounts>();
        var (restaurant, _) = await accounts.AddRestaurantAsync("Marokand (demo)");
        var info = app.Services.GetRequiredService<DemoMode>();
        await accounts.SaveAccountAsync(info.Phone, "Demo", info.Password, false, new[] { restaurant.Id });
        app.Logger.LogWarning("DEMO MODE: no database configured. Log in with {Phone} / {Password}", info.Phone, info.Password);

        // The made-up sales take a minute to build; the site is usable meanwhile.
        var restaurantId = restaurant.Id;
        _ = Task.Run(async () =>
        {
            try
            {
                await using (var tenant = app.Services.GetRequiredService<TenantDatabases>().Open(restaurantId))
                    await DemoData.SeedAsync(tenant);
                using var s2 = app.Services.CreateScope();
                var c2 = s2.ServiceProvider.GetRequiredService<CloudDbContext>();
                (await c2.Restaurants.FindAsync(restaurantId))!.LastSyncAt = DateTime.UtcNow;
                await c2.SaveChangesAsync();
                app.Logger.LogWarning("DEMO MODE: demo sales are ready");
            }
            catch (Exception ex) { app.Logger.LogError(ex, "Demo data failed"); }
        });
    }
}

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
    app.UseHttpsRedirection();
}
app.UseStaticFiles();
app.UseAuthentication();
app.UseAuthorization();
app.UseAntiforgery();

// ---------- sync from the restaurants ----------

app.MapGet("/api/ping", () => Results.Ok(new { service = "SwedPos Cloud", protocol = CloudSync.Protocol }));

app.MapPost("/api/sync", async (HttpContext http, SyncReceiver receiver, ILogger<Program> log) =>
{
    var restaurant = await receiver.FindAsync(http.Request.Headers["X-SwedPos-Key"]);
    if (restaurant is null) return Results.Json(new { error = "unknown key" }, statusCode: 401);
    SyncBatch? batch;
    try { batch = await JsonSerializer.DeserializeAsync<SyncBatch>(http.Request.Body, CloudSync.Json); }
    catch (JsonException) { return Results.BadRequest(new { error = "bad batch" }); }
    if (batch is null) return Results.BadRequest(new { error = "empty batch" });
    try
    {
        await receiver.ReceiveAsync(restaurant, batch);
        return Results.Ok(new { ok = true, orders = batch.Orders.Count });
    }
    catch (ValidationException ex) { return Results.BadRequest(new { error = ex.Message }); }
    catch (Exception ex)
    {
        log.LogError(ex, "Sync from restaurant {Id} failed", restaurant.Id);
        return Results.Json(new { error = "could not store the batch" }, statusCode: 500);
    }
}).DisableAntiforgery();

// ---------- login / logout / language ----------

app.MapGet("/logout", async (HttpContext http) =>
{
    await http.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
    return Results.Redirect("/" + Texts.Normalize(http.Request.Cookies["lang"]) + "/login");
});

app.MapGet("/lang/{code}", (HttpContext http, string code, string? to) =>
{
    http.Response.Cookies.Append("lang", Texts.Normalize(code), new CookieOptions { MaxAge = TimeSpan.FromDays(365), HttpOnly = true, SameSite = SameSiteMode.Lax });
    return Results.LocalRedirect(ChartMath.SafeLocal(to));
});

// Demo mode only: one click into the demo restaurant.
app.MapGet("/demo", async (HttpContext http, DemoMode info, CloudAccounts accounts, string? lang, string? page) =>
{
    if (!info.IsOn) return Results.NotFound();
    var account = await accounts.LoginAsync(info.Phone, info.Password);
    if (account is null) return Results.NotFound();
    await SignIn.RunAsync(http, account);
    return Results.Redirect("/" + Texts.Normalize(lang) + "/r/1/" + (ReportBuilder.Pages.Contains(page) ? page : "overview"));
});

// ---------- Excel export of the page on screen ----------

app.MapGet("/{lang}/r/{rid:int}/export/{page}", async (HttpContext http, string lang, int rid, string page, CloudAccounts accounts, TenantDatabases tenants) =>
{
    if (!int.TryParse(http.User.FindFirstValue(ClaimTypes.NameIdentifier), out var accountId)) return Results.Unauthorized();
    if ((await accounts.RestaurantsForAsync(accountId)).All(r => r.Id != rid)) return Results.Forbid();
    lang = Texts.Normalize(lang);
    var q = http.Request.Query;
    var today = RestaurantTime.Today;
    DateOnly Date(string key, DateOnly fallback) => DateOnly.TryParse(q[key], out var d) ? d : fallback;
    int? Id(string key) => int.TryParse(q[key], out var v) ? v : null;
    var filter = new AnalyticsFilter(Date("from", today.AddDays(-6)), Date("to", today), Id("hall"), Id("waiter"),
        Enum.TryParse<OrderType>(q["type"], out var type) ? type : null);
    var month = Date("month", new DateOnly(today.Year, today.Month, 1));

    await using var db = tenants.Open(rid);
    var built = await new ReportBuilder(db, lang).BuildAsync(page, filter, month);
    var path = Path.Combine(Path.GetTempPath(), "swedpos-cloud-" + Guid.NewGuid() + ".xlsx");
    var period = page == "payroll" ? month.ToString("MM.yyyy") : filter.From.ToString("dd.MM.yyyy") + " — " + filter.To.ToString("dd.MM.yyyy");
    ReportTableExporter.Save(path, "SwedPos · " + Texts.Get(lang, "an_page_" + page), period, built.Tables);
    var bytes = await File.ReadAllBytesAsync(path);
    File.Delete(path);
    return Results.File(bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "SwedPos_" + page + "_" + (page == "payroll" ? month.ToString("yyyy-MM") : filter.From.ToString("yyyy-MM-dd") + "_" + filter.To.ToString("yyyy-MM-dd")) + ".xlsx");
}).RequireAuthorization();

app.MapRazorComponents<App>().AddInteractiveServerRenderMode();
app.Run();

/// <summary>Signs a person in (used by the login page).</summary>
public static class SignIn
{
    public static Task RunAsync(HttpContext http, Account account)
    {
        var identity = new ClaimsIdentity(new[]
        {
            new Claim(ClaimTypes.NameIdentifier, account.Id.ToString()),
            new Claim(ClaimTypes.Name, account.Name),
            new Claim(ClaimTypes.MobilePhone, account.Phone)
        }, CookieAuthenticationDefaults.AuthenticationScheme);
        return http.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, new ClaimsPrincipal(identity),
            new AuthenticationProperties { IsPersistent = true });
    }
}

public partial class Program { }
