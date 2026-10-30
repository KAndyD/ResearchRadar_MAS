param(
    [string]$DocumentPath = "deliverables/ResearchRadar_MAS_Resource_Negotiation.docx"
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$docx = (Resolve-Path (Join-Path $root $DocumentPath)).Path
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $document = $word.Documents.Open($docx)
    try {
        $figures = @(
            @{ Anchor = 'FIGURE_ARCH'; File = 'docs/diagrams/lab3_architecture.svg'; Width = 440 },
            @{ Anchor = 'FIGURE_PROTOCOL'; File = 'docs/diagrams/lab3_protocol.svg'; Width = 440 },
            @{ Anchor = 'FIGURE_UTILITY'; File = 'experiments/lab3/results/utility.svg'; Width = 440 },
            @{ Anchor = 'FIGURE_FAIRNESS'; File = 'experiments/lab3/results/fairness.svg'; Width = 440 },
            @{ Anchor = 'FIGURE_MESSAGES'; File = 'experiments/lab3/results/messages.svg'; Width = 440 },
            @{ Anchor = 'FIGURE_WALL'; File = 'experiments/lab3/results/wall_time.svg'; Width = 440 }
        )
        foreach ($figure in $figures) {
            $range = $document.Content
            if (-not $range.Find.Execute($figure.Anchor)) {
                throw "Missing figure anchor: $($figure.Anchor)"
            }
            $range.Text = ''
            $svg = (Resolve-Path (Join-Path $root $figure.File)).Path
            $shape = $document.InlineShapes.AddPicture($svg, $false, $true, $range)
            $shape.Width = $figure.Width
        }
        $document.Save()
    }
    finally {
        $document.Close($false)
    }
}
finally {
    $word.Quit()
}
Write-Output $docx
