"""The upload service's settings."""

MAX_UPLOAD_MB = 8       # COUPLED:upload-limit: app
REQUEST_TIMEOUT_S = 60  # COUPLED:request-timeout: app
PORT = 8080             # COUPLED:port: app
METRICS_PORT = 9090     # COUPLED:port: metrics
# Google sends users back here after they sign in.
OAUTH_REDIRECT_URI = "https://uploads.example.com/auth/callback"  # COUPLED:oauth-redirect: app
