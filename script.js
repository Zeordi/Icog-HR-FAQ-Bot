document.getElementById('ask-btn').addEventListener('click', async () => {
    const question = document.getElementById('question').value;
    const chatBox = document.getElementById('chat-box');
    
    // Add the question to the chat
    const questionMessage = document.createElement('div');
    questionMessage.classList.add('message', 'question');
    questionMessage.textContent = question;
    chatBox.appendChild(questionMessage);
    
    // Clear the input field
    document.getElementById('question').value = '';
    
    // Send the question to the FastAPI backend
    const response = await fetch(`https://hr-fqa-latest-1.onrender.com/ask-hr?question=${encodeURIComponent(question)}`);
    const data = await response.json();
    
    // Add the response to the chat
    const responseMessage = document.createElement('div');
    responseMessage.classList.add('message', 'response');
    responseMessage.textContent = data.answer;
    chatBox.appendChild(responseMessage);
    
    // Scroll to the bottom of the chat box to show the latest message
    chatBox.scrollTop = chatBox.scrollHeight;
});
