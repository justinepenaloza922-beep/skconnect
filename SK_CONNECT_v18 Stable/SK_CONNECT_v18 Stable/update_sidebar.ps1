# Update all user templates to add Financial Reports sub-menu
$templateDir = "c:\Users\keinj\Downloads\SK_CONNECT_v17 Stable\SK_CONNECT_v17 Stable\templates"

$files = @(
    "sk_connect_user_dashboard.html",
    "sk_connect_user_announcement.html",
    "sk_connect_user_events_projects.html",
    "sk_connect_user_financial_report.html",
    "sk_connect_user_feedback.html",
    "sk_connect_user_document.html",
    "sk_connect_user_volunteer.html",
    "sk_connect_user_training.html",
    "sk_connect_user_community.html",
    "sk_connect_user_incident.html"
)

# Pattern 1: url_for style (most templates)
$oldPattern1 = @'
            <a href="{{ url_for('user_financial_report') }}" data-title="Financial Reports" class="sidebar-item flex items-center px-4 py-3 text-sm font-medium rounded-md">
              <i class="fas fa-chart-pie mr-3 text-lg"></i> Financial Reports
            </a>
'@

# Pattern 2: url_for with line break (document/training)
$oldPattern2 = @'
            <a href="{{ url_for('user_financial_report') }}" data-title="Financial Reports"
              class="sidebar-item flex items-center px-4 py-3 text-sm font-medium rounded-md">
              <i class="fas fa-chart-pie mr-3 text-lg"></i> Financial Reports
            </a>
'@

# Pattern 3: active-nav variant 
$oldPattern3 = @'
            <a href="{{ url_for('user_financial_report') }}" data-title="Financial Reports" class="sidebar-item active-nav flex items-center px-4 py-3 text-sm font-medium rounded-md">
              <i class="fas fa-chart-pie mr-3 text-lg"></i> Financial Reports
            </a>
'@

$replacement = @'
            <div class="relative" id="finDropdownWrap">
              <button id="finDropdownBtn" data-title="Financial Reports" class="sidebar-item flex items-center justify-between w-full px-4 py-3 text-sm font-medium rounded-md">
                <span class="flex items-center">
                  <i class="fas fa-chart-pie mr-3 text-lg"></i> Financial Reports
                </span>
                <i class="fas fa-chevron-down text-sm transition-transform" id="finChevron"></i>
              </button>
              <div id="finSubMenu" class="hidden pl-11 pr-2 py-1 space-y-1">
                <a href="{{ url_for('user_financial_report') }}" class="block px-3 py-2 text-sm text-blue-100 hover:text-white rounded-md">
                  <i class="fas fa-chart-bar mr-2"></i>Financial Dashboard
                </a>
                <a href="{{ url_for('user_financial_report') }}#transactions" class="block px-3 py-2 text-sm text-blue-100 hover:text-white rounded-md">
                  <i class="fas fa-receipt mr-2"></i>View Transactions
                </a>
                <a href="{{ url_for('user_financial_report') }}#projects" class="block px-3 py-2 text-sm text-blue-100 hover:text-white rounded-md">
                  <i class="fas fa-project-diagram mr-2"></i>View Projects
                </a>
              </div>
            </div>
'@

foreach ($file in $files) {
    $path = Join-Path $templateDir $file
    if (Test-Path $path) {
        $content = Get-Content $path -Raw
        $changed = $false
        
        if ($content.Contains("url_for('user_financial_report')") -and -not $content.Contains("finDropdownBtn")) {
            # Try each pattern
            if ($content.Contains($oldPattern3)) {
                $content = $content.Replace($oldPattern3, $replacement)
                $changed = $true
            }
            if ($content.Contains($oldPattern2)) {
                $content = $content.Replace($oldPattern2, $replacement)
                $changed = $true
            }
            if ($content.Contains($oldPattern1)) {
                $content = $content.Replace($oldPattern1, $replacement)
                $changed = $true
            }
            
            if ($changed) {
                Set-Content $path $content -NoNewline
                Write-Host "Updated: $file"
            } else {
                Write-Host "Pattern not matched: $file - manual update needed"
            }
        } else {
            Write-Host "Skipped: $file (already updated or not found)"
        }
    } else {
        Write-Host "Not found: $file"
    }
}

Write-Host "`nDone!"
