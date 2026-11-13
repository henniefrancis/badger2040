# Wrapper app: opens the shared badge code at section "a" (personal).
# The real work lives in /lib/badgekit.py; config is /henniefrancis/config/badge.json.
import badgekit

badgekit.run_section("a")
