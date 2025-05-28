Возможные варианты запуска

- pip + python
1. `pip install -r requirements.txt`
2. `python src/tg-app.py`

- conda
1. `conda create -n gpb_gpt_hack python=3.10`
2. `conda activate gpb_gpt_hack`
3. `pip install -r requirements.txt`
4. `python src/tg-app.py`

- docker
1. `docker compose up --wait --detach --build`