# Assignment 3 Public App Viewing & Deployment
The demo of the app can be viewed on render: https://airbnb-dashboard-vs5u.onrender.com/

## To deploy your own copy of the app: 
- clone the github repository
- create an account on render.com
- link your github account to render.com
- start a new web service and select your public repository

## web service settings:
| Setting | Value |
|---------|-------|
| **Runtime** | Python |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:server` |
| **Instance Type** | Free |

If the app as been idle it can take several minutes to load, sorry for the delay--maybe watch the video while it loads!  
