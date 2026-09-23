SHADOWBANE LOCATION LOOKUP

Start exactly one Shadowbane client, then double-click ShadowbaneLocationLookup.exe in the parent
folder. The tool finds Config\WorldDef.cfg beside the running sb.exe and opens an interactive prompt.
Enter a full location name, part of a name, or a close spelling. Type q to exit.

Advanced PowerShell use:

  .\Find-Shadowbane-Location.ps1 -Query "Black Drake Swamp"

  .\Find-Shadowbane-Location.ps1 -WorldDef 'C:\Path\To\Shadowbane\Config\WorldDef.cfg'

This release searches named WorldDef placements and the included confirmed destination overrides.
It includes runegates represented in those sources. It does not yet contain a rune-name-to-dropper
or rune-name-to-camp-location dataset.
