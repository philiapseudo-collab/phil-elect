# Vercel Deployment Guide

## Problem: Vercel CLI Installation Error (EBUSY)

The error you're seeing is a Windows file-lock issue with esbuild. Here are multiple solutions:

## Solution 1: Use npx (No Global Install Needed) ⭐ RECOMMENDED

You don't need to install Vercel CLI globally. Use `npx` instead:

```powershell
# Deploy without installing
npx vercel

# Or for production
npx vercel --prod
```

## Solution 2: Fix the Global Installation

### Step 1: Close all Node processes
```powershell
# Close VS Code, terminals, and any Node processes
taskkill /F /IM node.exe
```

### Step 2: Clear npm cache
```powershell
npm cache clean --force
```

### Step 3: Remove corrupted Vercel installation
```powershell
# Remove global vercel
npm uninstall -g vercel

# Remove the corrupted esbuild folder manually if needed
# (Navigate to: C:\Users\user\AppData\Roaming\npm\node_modules\vercel\node_modules\esbuild)
```

### Step 4: Reinstall as Administrator
1. Open PowerShell as Administrator
2. Run: `npm install -g vercel`

## Solution 3: Use GitHub Integration (No CLI Needed)

1. Push your code to GitHub
2. Go to [vercel.com](https://vercel.com)
3. Import your GitHub repository
4. Vercel will auto-detect Python and deploy

## Solution 4: Use Vercel Web Dashboard

1. Go to [vercel.com/dashboard](https://vercel.com/dashboard)
2. Click "Add New Project"
3. Drag and drop your project folder (or use CLI with npx)

## Quick Deploy Commands (Using npx)

```powershell
# First time setup (login)
npx vercel login

# Deploy to preview
npx vercel

# Deploy to production
npx vercel --prod

# Set environment variables
npx vercel env add OPENAI_API_KEY
npx vercel env add WHATSAPP_VERIFY_TOKEN
# ... etc for all variables from .env.example
```

## Environment Variables Setup

After deployment, set these in Vercel Dashboard:
- Settings → Environment Variables

Required variables (from `.env.example`):
- `OPENAI_API_KEY`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_API_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `MPESA_CONSUMER_KEY`
- `MPESA_CONSUMER_SECRET`

## Testing After Deployment

1. **Health Check**: `https://your-project.vercel.app/`
2. **Webhook Verification**: `https://your-project.vercel.app/api/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test123`

## Troubleshooting

If you still get EBUSY errors:
1. Disable antivirus temporarily during installation
2. Add npm folder to antivirus exclusions
3. Use Solution 1 (npx) - it doesn't require global install

