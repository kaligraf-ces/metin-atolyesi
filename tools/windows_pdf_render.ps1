param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [int]$FirstPage = 1,
    [int]$LastPage = 0
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime] | Out-Null

function Await-Operation($Operation, [Type]$ResultType) {
    $methods = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethodDefinition -and
            $_.GetParameters().Count -eq 1
        }
    $method = $methods[0].MakeGenericMethod($ResultType)
    $task = $method.Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

function Await-Action($Operation) {
    $methods = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            -not $_.IsGenericMethodDefinition -and
            $_.GetParameters().Count -eq 1
        }
    $task = $methods[0].Invoke($null, @($Operation))
    $task.Wait()
}

[System.IO.Directory]::CreateDirectory($OutputDir) | Out-Null
$pdfFullPath = [System.IO.Path]::GetFullPath($PdfPath)
$outFullPath = [System.IO.Path]::GetFullPath($OutputDir)

$pdfFile = Await-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($pdfFullPath)) ([Windows.Storage.StorageFile])
$document = Await-Operation ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($pdfFile)) ([Windows.Data.Pdf.PdfDocument])

$pageCount = [int]$document.PageCount
if ($LastPage -le 0 -or $LastPage -gt $pageCount) {
    $LastPage = $pageCount
}
if ($FirstPage -lt 1) {
    $FirstPage = 1
}

for ($pageNumber = $FirstPage; $pageNumber -le $LastPage; $pageNumber++) {
    $page = $document.GetPage([uint32]($pageNumber - 1))
    try {
        $outFile = Join-Path $outFullPath ("page_{0:D4}.png" -f $pageNumber)
        if (-not (Test-Path $outFile)) {
            [System.IO.File]::Create($outFile).Close()
        }
        $storageFile = Await-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($outFile)) ([Windows.Storage.StorageFile])
        $stream = Await-Operation ($storageFile.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            Await-Action ($page.RenderToStreamAsync($stream))
        }
        finally {
            $stream.Dispose()
        }
        Write-Output $outFile
    }
    finally {
        $page.Dispose()
    }
}
