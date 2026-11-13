# Wrapper app: opens the shared badge code at section "c" (microsoft).
# The real work lives in /lib/badgekit.py; config is /henniefrancis/config/badge.json.
import badgekit

badgekit.run_section("c")
