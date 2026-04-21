# Quick Deployment Guide - Performance Optimized

## Changes Summary

We've optimized the CV parser to reduce processing time from **28 seconds to 5-10 seconds** for warm requests.

### Key Optimizations:
1. ✅ Lazy loading of SpaCy model
2. ✅ Disabled unused NLP components (parser, NER)
3. ✅ Pre-compiled regex patterns
4. ✅ Optimized PDF text extraction
5. ✅ Added warmup endpoint

## Deploy to Render

### Option 1: Use Default Start Command (Recommended)
Keep the existing `render.yaml` as-is. After deployment:

1. **Immediately call the warmup endpoint**:
   ```bash
   curl https://your-app.onrender.com/warmup
   ```

2. **Monitor the first request**: Check logs - should see "CV parsed in X.XXs"

### Option 2: Auto-warmup on Startup
Update `render.yaml` to use the warmup script:

```yaml
startCommand: python start_with_warmup.py
```

This will automatically warmup the SpaCy model on deployment.

## Testing Locally

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the server**:
   ```bash
   python main_talendeur.py
   ```

3. **Test warmup**:
   ```bash
   # In another terminal
   curl http://localhost:8000/warmup
   ```

4. **Upload a test CV**:
   ```bash
   curl -X POST "http://localhost:8000/parse-cv" \
     -F "file=@test_cv.pdf"
   ```

5. **Check performance**: Look for "CV parsed in X.XXs" in console

## Expected Performance

| Scenario | Before | After | Improvement |
|----------|--------|-------|-------------|
| First request (cold) | 28s | 15-18s | ~40% faster |
| After warmup | 28s | 5-10s | ~70% faster |
| Subsequent requests | 28s | 5-10s | ~70% faster |

## Monitoring

### Check if warmup is active:
```bash
curl https://your-app.onrender.com/health
```

Response should include:
```json
{
  "status": "online",
  "nlp_loaded": true,
  "warmed_up": true
}
```

### View parse times:
Check Render logs for messages like:
```
CV parsed in 7.23s
```

## Keeping App Warm on Free Tier

Render's free tier sleeps after 15 minutes of inactivity. To prevent this:

### Option 1: External Pinger
Use a service like:
- [Uptime Robot](https://uptimerobot.com/) (free)
- [Cron-job.org](https://cron-job.org/en/) (free)

Ping your `/health` endpoint every 10 minutes.

### Option 2: GitHub Actions
Create `.github/workflows/keep-warm.yml`:

```yaml
name: Keep Render Warm
on:
  schedule:
    - cron: '*/10 * * * *'  # Every 10 minutes
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Ping health endpoint
        run: curl https://your-app.onrender.com/health
```

## Troubleshooting

### Still seeing 28s parse times?
1. Check if warmup was called: `curl https://your-app.onrender.com/health`
2. Verify `warmed_up: true` in response
3. Check Render logs for errors

### Memory issues?
SpaCy model uses ~200-300MB. This is fine for Render free tier (512MB).

### First request always slow?
This is normal for cold starts. Call `/warmup` immediately after deployment.

## Further Optimizations

If you need even faster performance:

1. **Upgrade to Render Paid Tier**: No cold starts, better CPU
2. **Cache results**: Store parsed CVs to avoid re-processing
3. **Profile code**: Use `cProfile` to find remaining bottlenecks
4. **Consider lighter NLP**: Replace SpaCy with rule-based parsing

## API Endpoints

- `POST /parse-cv` - Upload and parse a CV (multipart/form-data)
- `GET /health` - Health check (auto-warms up on first call)
- `GET /warmup` - Manually trigger SpaCy model loading
- `GET /docs` - Swagger UI documentation

## Support

For issues, check:
1. Render logs for error messages
2. Response times in logs ("CV parsed in X.XXs")
3. Health endpoint response
