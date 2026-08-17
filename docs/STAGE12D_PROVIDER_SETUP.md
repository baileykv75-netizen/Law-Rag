# Stage 12D — Provider Setup and Protected Secrets

Status: validation in progress.

Normal Windows desktop behavior:

- first normal launch queries local provider configuration state;
- if provider setup has not been completed and both providers are not already configured, the intake UI opens the guided setup dialog;
- DeepSeek and Kimi API keys are password inputs and are never returned to the browser after saving;
- Windows desktop persistence uses Windows Credential Manager generic credentials;
- development `DEEPSEEK_API_KEY` and `MOONSHOT_API_KEY` environment variables remain supported and take precedence;
- `runtime/config/provider-setup.json` stores only non-secret setup-completion state;
- connection tests are explicit and send one fixed, non-contract connectivity message to the selected provider;
- users may skip provider configuration and continue with local-only functionality;
- provider settings remain reopenable from the normal intake screen;
- startup diagnostics recognize protected provider configuration without exposing the credential value.

Validation requirements:

1. Linux/backend regressions and public quality gates remain green.
2. Locked frontend production build remains green.
3. Clean Windows runner performs a synthetic Credential Manager write/read/delete round trip.
4. The same Windows run rebuilds the onedir bundle and executes existing release/RC smoke tests.
5. No real API key, contract, runtime job, or provider response body is added to public CI artifacts.
