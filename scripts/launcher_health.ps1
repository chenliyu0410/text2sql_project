param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("check", "wait-and-open")]
    [string] $Mode
)

$url = "http://127.0.0.1:8765/"
$healthUrl = $url + "api/health"

function Test-PowerQueryHealth {
    $request = [Net.HttpWebRequest]::Create($healthUrl)
    $request.Method = "GET"
    $request.Timeout = 1000
    $request.ReadWriteTimeout = 1000
    $response = $null
    $reader = $null
    try {
        $response = [Net.HttpWebResponse] $request.GetResponse()
        if ([int] $response.StatusCode -ne 200) {
            return $false
        }
        $reader = [IO.StreamReader]::new($response.GetResponseStream(), [Text.Encoding]::UTF8)
        $body = $reader.ReadToEnd()
        return $body -match '"success"\s*:\s*true'
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $reader) {
            $reader.Dispose()
        }
        if ($null -ne $response) {
            $response.Dispose()
        }
    }
}

if ($Mode -eq "check") {
    if (Test-PowerQueryHealth) {
        exit 0
    }
    exit 1
}

for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if (Test-PowerQueryHealth) {
        $startInfo = [Diagnostics.ProcessStartInfo]::new($url)
        $startInfo.UseShellExecute = $true
        $browser = [Diagnostics.Process]::Start($startInfo)
        if ($null -ne $browser) {
            $browser.Dispose()
        }
        exit 0
    }
    [Threading.Thread]::Sleep(500)
}
exit 1
