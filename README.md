# Bistro

Bistro is a simple recipe search and management application. It allows you to find recipes for cocktails and meals using free online databases, organize your favorite recipes in a personal collection, and manage your shopping list.

## Features

- **Recipe Search**: Search for meals from a vast database.
- **Cocktail Search**: Find recipes for your favorite drinks.
- **My Collection**: Save your favorite recipes for easy access.
- **Add Recipes**: Manually add your own recipes to the collection.
- **Shopping List**: Keep track of ingredients you need to buy.
- **Adaptive UI**: Built with GTK4 and Libadwaita, the interface adapts to different screen sizes and supports light/dark themes.

## Technologies

- **Python 3**: The core programming language.
- **GTK4 & Libadwaita**: For a modern, adaptive user interface.
- **PyGObject**: Python bindings for GObject-based libraries.
- **Requests**: For API interactions.

## Installation and Usage

### Prerequisites

Ensure you have Python 3 and the necessary system dependencies for GTK4 and Libadwaita installed.

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Application

```bash
python3 main.py
```

## Structure

- `main.py`: The entry point of the application.
- `bistro/`: Contains the source code.
  - `app.py`: The main application class.
  - `window.py`: The main window setup.
  - `pages/`: Individual pages for Search, Collection, Shopping List, etc.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
