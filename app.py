from flask import Flask, render_template

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')
# def hello_world():  # put application's code here
#     return 'Hello World 3!'


if __name__ == '__main__':
    app.run()
