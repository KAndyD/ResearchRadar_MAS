$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$docx = Join-Path $root 'deliverables\ResearchRadar_MAS_Reliability_Assessment.docx'
$pdf = Join-Path $root 'deliverables\ResearchRadar_MAS_Reliability_Assessment.pdf'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    Write-Output 'Opening DOCX'
    $document = $word.Documents.Open($docx, $false, $true)
    try {
        Write-Output 'Exporting PDF'
        $document.ExportAsFixedFormat($pdf, 17)
    }
    finally { $document.Close(0) }
}
finally { $word.Quit() }
Write-Output $pdf
