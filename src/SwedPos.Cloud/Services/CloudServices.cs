using System.Security.Cryptography;
using System.Text;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using SwedPos.Cloud.Data;
using SwedPos.Data;
using SwedPos.Services;

namespace SwedPos.Cloud.Services;

/// <summary>
/// One PostgreSQL database per restaurant, with exactly the desktop's schema (same migrations), so the shared
/// AnalyticsService runs on it unchanged. Restaurants never share tables.
/// </summary>
public class TenantDatabases
{
    private readonly string _server;

    /// <param name="server">Connection string to the PostgreSQL server (any database); the user needs CREATEDB.</param>
    public TenantDatabases(string server) => _server = server;

    public static string DatabaseName(int restaurantId) => "swedpos_cloud_r" + restaurantId;

    public string ConnectionString(int restaurantId) =>
        new NpgsqlConnectionStringBuilder(_server) { Database = DatabaseName(restaurantId) }.ToString();

    public virtual SwedPosDbContext Open(int restaurantId) =>
        new(new DbContextOptionsBuilder<SwedPosDbContext>().UseNpgsql(ConnectionString(restaurantId)).Options);

    /// <summary>Creates the restaurant's database if missing and brings its schema up to date.</summary>
    public virtual async Task EnsureAsync(int restaurantId)
    {
        var name = DatabaseName(restaurantId);
        await using (var conn = new NpgsqlConnection(new NpgsqlConnectionStringBuilder(_server) { Database = "postgres" }.ToString()))
        {
            await conn.OpenAsync();
            await using var check = new NpgsqlCommand("SELECT 1 FROM pg_database WHERE datname = @n", conn);
            check.Parameters.AddWithValue("n", name);
            if (await check.ExecuteScalarAsync() is null)
            {
                // The name is built from a number only, so it is safe to put into the statement.
                await using var create = new NpgsqlCommand("CREATE DATABASE \"" + name + "\"", conn);
                await create.ExecuteNonQueryAsync();
            }
        }
        await using var db = Open(restaurantId);
        await db.Database.MigrateAsync();
    }
}

/// <summary>Demo mode (no database configured): every restaurant lives in memory.</summary>
public class DemoTenants : TenantDatabases
{
    private readonly Microsoft.EntityFrameworkCore.Storage.InMemoryDatabaseRoot _root;
    public DemoTenants(Microsoft.EntityFrameworkCore.Storage.InMemoryDatabaseRoot root) : base("Host=demo") => _root = root;

    public override SwedPosDbContext Open(int restaurantId) =>
        new(new DbContextOptionsBuilder<SwedPosDbContext>().UseInMemoryDatabase(DatabaseName(restaurantId), _root).Options);

    public override async Task EnsureAsync(int restaurantId)
    {
        await using var db = Open(restaurantId);
        await db.Database.EnsureCreatedAsync();
    }
}

/// <summary>Set when the site runs without a database, on demo data.</summary>
public sealed record DemoMode(bool IsOn, string Phone = "", string Password = "");

/// <summary>Sync keys: random, shown once, stored only as a hash.</summary>
public static class SyncKeys
{
    public static string New() => "spk_" + Convert.ToBase64String(RandomNumberGenerator.GetBytes(30)).Replace('+', '-').Replace('/', '_').TrimEnd('=');

    public static string Hash(string key) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(key.Trim())));
}

public static class Phone
{
    /// <summary>"+998 90 123-45-67", "901234567" → "998901234567". Null when it cannot be a phone number.</summary>
    public static string? Normalize(string? input)
    {
        var digits = new string((input ?? "").Where(char.IsAsciiDigit).ToArray());
        if (digits.Length == 9) digits = "998" + digits;
        return digits.Length is >= 11 and <= 15 ? digits : null;
    }
}

/// <summary>Restaurants and accounts (used by the admin commands and the login).</summary>
public class CloudAccounts
{
    private readonly CloudDbContext _db;
    private readonly TenantDatabases _tenants;

    public CloudAccounts(CloudDbContext db, TenantDatabases tenants) { _db = db; _tenants = tenants; }

    /// <summary>Creates a restaurant and its database. Returns the sync key (shown only this once).</summary>
    public async Task<(Restaurant Restaurant, string Key)> AddRestaurantAsync(string name)
    {
        if (string.IsNullOrWhiteSpace(name)) throw new ValidationException("name_required");
        var key = SyncKeys.New();
        var restaurant = new Restaurant { Name = name.Trim(), KeyHash = SyncKeys.Hash(key), KeyPrefix = key[..10] };
        _db.Restaurants.Add(restaurant);
        await _db.SaveChangesAsync();
        await _tenants.EnsureAsync(restaurant.Id);
        return (restaurant, key);
    }

    /// <summary>A new key for a restaurant (the old one stops working at once).</summary>
    public async Task<string> RenewKeyAsync(int restaurantId)
    {
        var r = await _db.Restaurants.FindAsync(restaurantId) ?? throw new ValidationException("not_found");
        var key = SyncKeys.New();
        r.KeyHash = SyncKeys.Hash(key);
        r.KeyPrefix = key[..10];
        await _db.SaveChangesAsync();
        return key;
    }

    /// <summary>Creates or updates an account and gives it access to the listed restaurants.</summary>
    public async Task<Account> SaveAccountAsync(string phone, string name, string? password, bool isAdmin, IEnumerable<int> restaurantIds)
    {
        var number = Phone.Normalize(phone) ?? throw new ValidationException("phone_invalid");
        var account = await _db.Accounts.Include(a => a.Restaurants).FirstOrDefaultAsync(a => a.Phone == number);
        if (account is null)
        {
            if (string.IsNullOrEmpty(password)) throw new ValidationException("password_required");
            account = new Account { Phone = number };
            _db.Accounts.Add(account);
        }
        if (!string.IsNullOrEmpty(password))
        {
            if (password.Length < 8) throw new ValidationException("password_short");
            account.PasswordHash = PinHasher.Hash(password);
        }
        account.Name = string.IsNullOrWhiteSpace(name) ? account.Name : name.Trim();
        account.IsAdmin = isAdmin;
        foreach (var id in restaurantIds.Distinct())
            if (account.Restaurants.All(x => x.RestaurantId != id)) account.Restaurants.Add(new AccountRestaurant { RestaurantId = id });
        await _db.SaveChangesAsync();
        return account;
    }

    /// <summary>The account for this phone and password, or null. The answer takes the same time either way.</summary>
    public async Task<Account?> LoginAsync(string phone, string password)
    {
        var number = Phone.Normalize(phone);
        var account = number is null ? null : await _db.Accounts.FirstOrDefaultAsync(a => a.Phone == number && a.IsActive);
        var ok = PinHasher.Verify(password ?? "", account?.PasswordHash ?? PinHasher.Hash("not-a-real-password"));
        if (account is null || !ok) return null;
        account.LastLoginAt = DateTime.UtcNow;
        await _db.SaveChangesAsync();
        return account;
    }

    /// <summary>Restaurants this account may see (admins: all).</summary>
    public async Task<List<Restaurant>> RestaurantsForAsync(int accountId)
    {
        var account = await _db.Accounts.AsNoTracking().FirstOrDefaultAsync(a => a.Id == accountId && a.IsActive);
        if (account is null) return new();
        var q = _db.Restaurants.AsNoTracking().Where(r => r.IsActive);
        if (!account.IsAdmin) q = q.Where(r => _db.AccountRestaurants.Any(x => x.AccountId == accountId && x.RestaurantId == r.Id));
        return await q.OrderBy(r => r.Name).ToListAsync();
    }
}

/// <summary>Receives a restaurant's batch and stores it in its database.</summary>
public class SyncReceiver
{
    private readonly CloudDbContext _db;
    private readonly TenantDatabases _tenants;

    public SyncReceiver(CloudDbContext db, TenantDatabases tenants) { _db = db; _tenants = tenants; }

    /// <summary>Null when the key is unknown.</summary>
    public async Task<Restaurant?> FindAsync(string? key)
    {
        if (string.IsNullOrWhiteSpace(key)) return null;
        var hash = SyncKeys.Hash(key);
        return await _db.Restaurants.FirstOrDefaultAsync(r => r.KeyHash == hash && r.IsActive);
    }

    public async Task ReceiveAsync(Restaurant restaurant, SyncBatch batch)
    {
        await using (var tenant = _tenants.Open(restaurant.Id))
            await new CloudSyncApplier(tenant).ApplyAsync(batch);
        restaurant.LastSyncAt = DateTime.UtcNow;
        restaurant.LastAppVersion = batch.AppVersion;
        await _db.SaveChangesAsync();
    }
}
