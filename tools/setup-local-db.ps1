# One-time setup of a local PostgreSQL for SwedPos Cloud (development / testing on this PC).
# Creates the login role "swedpos_cloud" (allowed to create the per-restaurant databases) and the control database,
# then stores the connection strings in .NET user-secrets (never in the repository).
# psql asks for the "postgres" password itself; this script never sees it.

$ErrorActionPreference = "Stop"
$psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $psql) { throw "psql.exe not found. Is PostgreSQL installed?" }

# A random password for the site's own database role.
$bytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$password = [Convert]::ToBase64String($bytes).Replace("+", "x").Replace("/", "y").Replace("=", "")

$sql = @"
DO `$`$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'swedpos_cloud') THEN
    ALTER ROLE swedpos_cloud LOGIN CREATEDB PASSWORD '$password';
  ELSE
    CREATE ROLE swedpos_cloud LOGIN CREATEDB PASSWORD '$password';
  END IF;
END `$`$;
"@
Write-Host "PostgreSQL will now ask for the password of the 'postgres' user."
& $psql.FullName -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c $sql
& $psql.FullName -U postgres -h localhost -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'swedpos_cloud'" | Out-String | ForEach-Object {
    if ($_.Trim() -ne "1") { & $psql.FullName -U postgres -h localhost -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE swedpos_cloud OWNER swedpos_cloud" }
}

$project = Join-Path $PSScriptRoot "..\src\SwedPos.Cloud"
dotnet user-secrets --project $project set "ConnectionStrings:Control" "Host=localhost;Port=5432;Database=swedpos_cloud;Username=swedpos_cloud;Password=$password" | Out-Null
dotnet user-secrets --project $project set "ConnectionStrings:Server" "Host=localhost;Port=5432;Database=postgres;Username=swedpos_cloud;Password=$password" | Out-Null
Write-Host "Done. 'dotnet run --project src/SwedPos.Cloud' now uses PostgreSQL. Next: add-restaurant and add-account (see README)."
