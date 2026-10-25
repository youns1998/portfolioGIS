param([string]$BrowserPath,[string]$BaseUrl='http://127.0.0.1:8787/',[string]$ScreenshotDir)
$Mode='gis'

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $ScreenshotDir) { $ScreenshotDir=Join-Path $root '.codex-preview/screenshots' }
if ($BaseUrl) { $BaseUrl = $BaseUrl.TrimEnd('/') + '/' }
if (-not $BrowserPath) {
    $BrowserPath = @(
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $BrowserPath) { throw 'Install Chrome or Edge, or supply -BrowserPath.' }
$profile = Join-Path $root ('.codex-preview/browser-' + [guid]::NewGuid().ToString('N'))
$socket = [Net.WebSockets.ClientWebSocket]::new()
$script:commandId = 0
$script:failures = [Collections.Generic.List[string]]::new()
$script:browserErrors = [Collections.Generic.List[string]]::new()
$script:checks = 0

function Send-Cdp($Method, $Parameters = @{}) {
    $script:commandId++
    $id = $script:commandId
    $json = @{ id = $id; method = $Method; params = $Parameters } | ConvertTo-Json -Depth 20 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $null = $socket.SendAsync([ArraySegment[byte]]::new($bytes), [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    while ($true) {
        $stream = [IO.MemoryStream]::new()
        $cancel = [Threading.CancellationTokenSource]::new(20000)
        try {
            do {
                $buffer = New-Object byte[] 65536
                $message = $socket.ReceiveAsync([ArraySegment[byte]]::new($buffer), $cancel.Token).GetAwaiter().GetResult()
                if ($message.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) { throw 'Browser disconnected.' }
                $stream.Write($buffer, 0, $message.Count)
            } while (-not $message.EndOfMessage)
            $payload = [Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
        } finally { $stream.Dispose(); $cancel.Dispose() }
        if ($payload.method -eq 'Runtime.exceptionThrown') { $script:browserErrors.Add(($payload.params | ConvertTo-Json -Depth 8 -Compress)) }
        if ($payload.method -eq 'Log.entryAdded' -and $payload.params.entry.level -eq 'error') { $script:browserErrors.Add($payload.params.entry.text) }
        if ($payload.id -eq $id) {
            if ($payload.error) { throw ($payload.error | ConvertTo-Json -Compress) }
            return $payload.result
        }
    }
}

function Invoke-Js($Expression) {
    $result = Send-Cdp 'Runtime.evaluate' @{ expression = $Expression; returnByValue = $true; awaitPromise = $true }
    if ($result.exceptionDetails) { throw ($result.exceptionDetails | ConvertTo-Json -Depth 8) }
    return $result.result.value
}

function Open-Page($Path) {
    if (-not $ScreenshotDir) { $ScreenshotDir=Join-Path $root '.codex-preview/screenshots' }
if ($BaseUrl) {
        $url = [uri]::new([uri]$BaseUrl, $Path).AbsoluteUri
    } else {
        $parts = $Path -split '\?', 2
        $url = ([uri](Join-Path $root ('docs/' + $parts[0]))).AbsoluteUri
        if ($parts.Count -gt 1) { $url += '?' + $parts[1] }
    }
    $navigation = Send-Cdp 'Page.navigate' @{ url = $url }
    if ($navigation.errorText) { throw $navigation.errorText }
    # Wait until the new document has replaced the previous execution context.
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        Start-Sleep -Milliseconds 100
        try {
            if (Invoke-Js ('location.href === ' + (ConvertTo-Json $url -Compress) + ' && document.readyState === "complete"')) { break }
        } catch { if ($attempt -eq 99) { throw } }
    }
    if ($attempt -eq 100) { throw "Page did not finish loading: $Path" }
    $null = Invoke-Js 'Promise.all([...document.images].map(i => { i.loading = "eager"; return i.decode().catch(() => {}); })).then(() => document.fonts.ready).then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))))'
}

function Assert-Js($Name, $Expression) {
    $script:checks++
    if ((Invoke-Js $Expression) -ne $true) { $script:failures.Add($Name); Write-Host "FAIL $Name" }
}

function Set-Viewport($Width) {
    $null = Send-Cdp 'Emulation.setDeviceMetricsOverride' @{ width = $Width; height = 900; deviceScaleFactor = 1; mobile = $false }
}

try {
    $browser = Start-Process $BrowserPath -ArgumentList @('--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=0', ('--user-data-dir="' + $profile + '"'), 'about:blank') -WindowStyle Hidden -PassThru
    $portFile = Join-Path $profile 'DevToolsActivePort'
    for ($attempt = 0; $attempt -lt 100 -and -not (Test-Path -LiteralPath $portFile); $attempt++) { Start-Sleep -Milliseconds 100 }
    if (-not (Test-Path -LiteralPath $portFile)) { throw 'Browser debugging endpoint did not start.' }
    $port = (Get-Content -LiteralPath $portFile)[0]
    $tabs = Invoke-RestMethod "http://127.0.0.1:$port/json/list"
    $tab = $tabs | Where-Object type -eq 'page' | Select-Object -First 1
    $null = $socket.ConnectAsync([uri]$tab.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    $null = Send-Cdp 'Runtime.enable'
    $null = Send-Cdp 'Log.enable'
    $null = Send-Cdp 'Page.enable'
    $null = Send-Cdp 'Emulation.setEmulatedMedia' @{ features = @(@{ name = 'prefers-reduced-motion'; value = 'no-preference' }) }


    New-Item -ItemType Directory -Path $ScreenshotDir -Force | Out-Null
    if($Mode -eq 'spring') {
        Set-Viewport 1440
        Open-Page 'workspace/login'
        Assert-Js 'Spring login has CSRF protection' '!!document.querySelector("input[name=_csrf]")'
        $null=Invoke-Js 'document.querySelector("#username").value="editor";document.querySelector("#password").value="Portfolio-2026!";document.querySelector("form").requestSubmit();true'
        Start-Sleep -Milliseconds 700
        foreach($width in @(1440,390)) {
            Set-Viewport $width
            Open-Page 'workspace'
            Assert-Js "Authenticated dashboard at $width" 'document.querySelector("h1").textContent.includes("사업 현황") && document.querySelectorAll("tbody tr").length>=4 && document.querySelectorAll(".stats strong").length===4'
            Assert-Js "Spring fits viewport at $width" 'document.documentElement.scrollWidth<=innerWidth'
            Assert-Js "Editor actions and sample disclaimer at $width" '!!document.querySelector("a[href=\"/workspace/projects/new\"]") && document.querySelector("footer").textContent.includes("가상 데이터")'
            $shot=Send-Cdp 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$true}
            [IO.File]::WriteAllBytes((Join-Path $ScreenshotDir ('workspace-'+$width+'.png')),[Convert]::FromBase64String($shot.data))
            Open-Page 'workspace/projects/new'
            Assert-Js "Project form and date fields at $width" '!!document.querySelector("#code") && document.querySelectorAll("input[type=date]").length===2 && !!document.querySelector("input[name=_csrf]") && document.documentElement.scrollWidth<=innerWidth'
            Open-Page 'workspace/projects/1'
            Assert-Js "Task workflow and history at $width" 'document.querySelectorAll(".task").length===3 && document.querySelectorAll(".history li").length>=4 && !!document.querySelector(".status-form input[name=version]") && document.documentElement.scrollWidth<=innerWidth'
        }
        Set-Viewport 1440
        Open-Page 'workspace/projects/1'
        $shot=Send-Cdp 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$true}
        [IO.File]::WriteAllBytes((Join-Path $ScreenshotDir 'project-detail.png'),[Convert]::FromBase64String($shot.data))
        Open-Page 'workspace?q=no-such-project-qa'
        Assert-Js 'Search empty state' '!!document.querySelector(".empty") && document.querySelector(".empty").textContent.includes("없습니다")'
        Open-Page 'workspace/login'
        $null=Invoke-Js 'document.querySelector("#username").value="viewer";document.querySelector("#password").value="View-2026!";document.querySelector("form").requestSubmit();true'
        Start-Sleep -Milliseconds 500
        Open-Page 'workspace'
        Assert-Js 'Viewer has no create action' 'document.querySelector("h1").textContent.includes("사업 현황") && !document.querySelector("a[href=\"/workspace/projects/new\"]")'
    } else {
        foreach($width in @(1440,390)) {
            Set-Viewport $width
            Open-Page 'index.html'
            Assert-Js "GIS has complete results at $width" 'document.querySelector("#total").textContent==="36" && document.querySelector("#high").textContent==="7" && document.querySelectorAll("#rows tr").length===36'
            Assert-Js "GIS fits viewport at $width" 'document.documentElement.scrollWidth<=innerWidth'
            $shot=Send-Cdp 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$true}
            [IO.File]::WriteAllBytes((Join-Path $ScreenshotDir ('map-'+$width+'.png')),[Convert]::FromBase64String($shot.data))
            if($width -eq 1440){ $overview=Send-Cdp 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false};[IO.File]::WriteAllBytes((Join-Path $ScreenshotDir 'map-overview.png'),[Convert]::FromBase64String($overview.data)) }
            Assert-Js "Priority filtering updates map and table at $width" 'document.querySelector("#priority").value="P1";document.querySelector("#priority").dispatchEvent(new Event("input"));document.querySelectorAll("#rows tr").length===7 && document.querySelectorAll(".asset:not([hidden])").length===7'
            Assert-Js "Map selection shows evidence at $width" 'document.querySelector(".asset:not([hidden])").dispatchEvent(new MouseEvent("click"));document.querySelector("#detail").textContent.includes("점검 근거")'
            Assert-Js "Search empty state at $width" 'document.querySelector("#search").value="does-not-exist";document.querySelector("#search").dispatchEvent(new Event("input"));document.querySelectorAll(".asset:not([hidden])").length===0 && !!document.querySelector(".empty")'
        }
    }
    if($script:browserErrors.Count){$script:failures.Add(($script:browserErrors -join '; '))}
    if($script:failures.Count){throw ($script:failures -join '; ')}
    Write-Host "Passed $($script:checks) $Mode browser checks."
} finally {
    $socket.Dispose()
    if($browser -and -not $browser.HasExited){Stop-Process -Id $browser.Id -ErrorAction SilentlyContinue}
}
