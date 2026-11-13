# Wrapper app: opens the shared badge code at section "a" (profile).
# The real work lives in /lib/badgekit.py; config is /badge/config/badge.json.
import badgekit

badgekit.run_section("a")
