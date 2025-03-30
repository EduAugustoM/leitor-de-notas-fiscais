async function process_invoice() {
    const button = document.querySelector('.btn');
    const fileInput = document.getElementById('fileInput');
    const output = document.getElementById('output');
  
    if (fileInput.files.length === 0) {
      alert('Por favor, selecione ao menos uma imagem');
      return;
    }
    
    // Desabilitar o botão e ajustar o estilo enquanto processa
    button.disabled = true;
    button.style.opacity = 0.5;
    output.innerText = "Processando...";
  
    const formData = new FormData();
    // Adiciona todos os arquivos selecionados ao FormData
    for (let i = 0; i < fileInput.files.length; i++) {
      formData.append('file', fileInput.files[i]);
    }
  
    try {
      const response = await fetch('/api/v1/invoice', {
        method: 'POST',
        body: formData
      });
      if (!response.ok) {
        output.innerText = "Erro ao processar a imagem: " + response.statusText;
        return;
      }
      const data = await response.json();
      output.innerText = JSON.stringify(data, null, 2);
    } catch (error) {
      output.innerText = "Erro na requisição: " + error;
    } finally {
      // Reabilitar o botão após a conclusão da requisição
      button.disabled = false;
      button.style.opacity = 1;
    }
  }