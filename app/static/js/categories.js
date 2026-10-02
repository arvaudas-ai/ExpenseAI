document.addEventListener('DOMContentLoaded', () => {
    const createForm = document.getElementById('create-category-form');
    const editForm = document.getElementById('edit-category-form');
    const categoriesList = document.getElementById('categories-list');
    const formMessage = document.getElementById('form-message');
    const editModal = document.getElementById('edit-modal');
    const closeModalBtn = document.getElementById('close-modal');
    const logoutButton = document.getElementById('logout-btn');

    const token = localStorage.getItem('expenseai_token') || localStorage.getItem('access_token');

    if (!token) {
        window.location.href = '/login';
        return;
    }

    logoutButton.addEventListener('click', () => {
        localStorage.removeItem('expenseai_token');
        localStorage.removeItem('access_token');
        window.location.href = '/login';
    });

    // Icon mapping for emoji display
    const iconMap = {
        'food': '🍔',
        'transport': '🚗',
        'utilities': '💡',
        'entertainment': '🎬',
        'shopping': '🛍️',
        'health': '⚕️',
        'education': '📚',
        'travel': '✈️',
        'dining': '🍽️',
        'groceries': '🛒',
        'gas': '⛽',
        'electricity': '⚡',
        'water': '💧',
        'internet': '📶',
        'phone': '📱',
        'movie': '🎥',
        'music': '🎵',
        'books': '📖',
        'sports': '⚽',
        'gym': '🏋️',
        'medical': '🏥',
        'pharmacy': '💊',
        'doctor': '👨‍⚕️',
        'school': '🎓',
        'tuition': '🎓',
        'plane': '✈️',
        'hotel': '🏨',
        'taxi': '🚕',
        'other': '📌'
    };

    // Setup color picker for create form
    setupColorPicker('color-palette', 'category-color');
    
    // Setup color picker for edit form
    setupColorPicker('edit-color-palette', 'edit-category-color');

    function setupColorPicker(paletteId, colorInputId) {
        const colorButtons = document.getElementById(paletteId).querySelectorAll('.color-option');
        const colorInput = document.getElementById(colorInputId);

        colorButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const color = button.getAttribute('data-color');
                colorInput.value = color;

                // Visual feedback - highlight selected color
                colorButtons.forEach(btn => btn.style.border = 'none');
                button.style.border = '3px solid #333';
            });
        });

        // Set initial border on the first/default color
        colorButtons.forEach(btn => {
            if (btn.getAttribute('data-color') === colorInput.value) {
                btn.style.border = '3px solid #333';
            }
        });
    }

    // Load categories on page load
    loadCategories();

    // Create category form submission
    createForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const name = document.getElementById('category-name').value.trim();
        const icon = document.getElementById('category-icon').value;
        const color = document.getElementById('category-color').value;

        if (!name || !icon) {
            showMessage('Please fill in all fields', 'error');
            return;
        }

        try {
            const response = await fetch('/api/categories', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ name, icon, color })
            });

            if (!response.ok) {
                const data = await response.json();
                showMessage(data.detail || 'Failed to create category', 'error');
                return;
            }

            showMessage('Category created successfully!', 'success');
            createForm.reset();
            document.getElementById('category-icon').value = '';
            document.getElementById('category-color').value = '#FF6B6B';
            setupColorPicker('color-palette', 'category-color');
            loadCategories();
        } catch (error) {
            showMessage('Error creating category: ' + error.message, 'error');
        }
    });

    // Edit category form submission
    editForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const categoryId = document.getElementById('edit-category-id').value;
        const name = document.getElementById('edit-category-name').value.trim();
        const icon = document.getElementById('edit-category-icon').value;
        const color = document.getElementById('edit-category-color').value;

        if (!name || !icon) {
            showMessage('Please fill in all fields', 'error');
            return;
        }

        try {
            const response = await fetch(`/api/categories/${categoryId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ name, icon, color })
            });

            if (!response.ok) {
                const data = await response.json();
                showMessage(data.detail || 'Failed to update category', 'error');
                return;
            }

            showMessage('Category updated successfully!', 'success');
            editModal.hidden = true;
            loadCategories();
        } catch (error) {
            showMessage('Error updating category: ' + error.message, 'error');
        }
    });

    // Close modal button
    closeModalBtn.addEventListener('click', () => {
        editModal.hidden = true;
    });

    // Delete category button
    document.getElementById('delete-category-btn').addEventListener('click', async (e) => {
        e.preventDefault();
        const categoryId = document.getElementById('edit-category-id').value;

        if (!confirm('Are you sure you want to delete this category?')) {
            return;
        }

        try {
            const response = await fetch(`/api/categories/${categoryId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                const data = await response.json();
                showMessage(data.detail || 'Failed to delete category', response.status === 409 ? 'warning' : 'error');
                return;
            }

            showMessage('Category deleted successfully!', 'success');
            editModal.hidden = true;
            loadCategories();
        } catch (error) {
            showMessage('Error deleting category: ' + error.message, 'error');
        }
    });

    async function loadCategories() {
        try {
            const response = await fetch('/api/categories', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                throw new Error('Failed to load categories');
            }

            const categories = await response.json();

            if (categories.length === 0) {
                categoriesList.innerHTML = '<p class="no-items">No categories found.</p>';
                return;
            }

            categoriesList.innerHTML = categories.map(category => `
                <div class="category-card" style="border-left: 4px solid ${category.color};">
                    <div class="category-header">
                        <span class="category-icon">${iconMap[category.icon] || '📌'}</span>
                        <span class="category-name">${escapeHtml(category.name)}</span>
                        ${category.is_default ? '<span class="category-badge">Default</span>' : ''}
                    </div>
                    <div class="category-color" style="background-color: ${category.color};"></div>
                    ${!category.is_default ? `
                        <button type="button" class="category-edit-btn" data-id="${category.id}">Edit</button>
                    ` : ''}
                </div>
            `).join('');

            // Add event listeners to edit buttons
            document.querySelectorAll('.category-edit-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    openEditModal(categories.find(c => c.id == btn.getAttribute('data-id')));
                });
            });
        } catch (error) {
            categoriesList.textContent = `Error loading categories: ${error.message}`;
            categoriesList.className = 'categories-grid error-message';
        }
    }

    function openEditModal(category) {
        document.getElementById('edit-category-id').value = category.id;
        document.getElementById('edit-category-name').value = category.name;
        document.getElementById('edit-category-icon').value = category.icon;
        document.getElementById('edit-category-color').value = category.color;

        // Update color picker selection
        const colorButtons = document.getElementById('edit-color-palette').querySelectorAll('.color-option');
        colorButtons.forEach(btn => {
            if (btn.getAttribute('data-color') === category.color) {
                btn.style.border = '3px solid #333';
            } else {
                btn.style.border = 'none';
            }
        });

        editModal.hidden = false;
    }

    function showMessage(text, type) {
        formMessage.textContent = text;
        formMessage.className = `form-message ${type}`;
        setTimeout(() => {
            formMessage.textContent = '';
            formMessage.className = 'form-message';
        }, 4000);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});
