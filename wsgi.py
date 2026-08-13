from main import app, start_background_sync

start_background_sync()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
