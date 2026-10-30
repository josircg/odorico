async function inicializeFilters(cursoId) {
    try {
        const response = await fetch(`/admin/nucleo/orientacao/fields/curso/${cursoId}/chain/`);
        const data = await response.json();

        const alunoSelect = document.getElementById('id_aluno');
        // Armazenar os valores selecionados atuais
        const selectedAluno = alunoSelect.value;

        // Limpar os selects somente se eles não tiverem um valor selecionado
        alunoSelect.innerHTML = '';
        const defaultAlunoOption = document.createElement('option');
        defaultAlunoOption.value = '';
        defaultAlunoOption.text = '--------';
        alunoSelect.appendChild(defaultAlunoOption);

        // Populando o select de alunos
        data.alunos.forEach(aluno => {
            const option = document.createElement('option');
            option.value = aluno.value;
            option.text = aluno.label;
            alunoSelect.appendChild(option);
        });

        // Restaurar o valor selecionado se estiver nos novos dados
        if (data.alunos.some(aluno => aluno.value === parseInt(selectedAluno))) {
            alunoSelect.value = selectedAluno;
        }

    } catch (error) {
        console.error('Erro ao buscar os dados:', error);
    }
}

window.addEventListener('load', function () {
    console.log('Widgets dos forms foram inicializados');

    const cursoField = document.getElementById('id_curso');
    const alunoSelect = document.getElementById('id_aluno');
    const coorientacao = document.getElementById("id_coorientacao");

    coorientacao.addEventListener("change", function(e) {
        e.target.value = e.target.checked // envia sempre true ou false para o django-select2 enviar para a view de autocomplete
    });

    // Limpar os selects ao carregar a página
    if (!alunoSelect.value) {
        alunoSelect.innerHTML = '<option value="">--------</option>';
    }

    if (cursoField) {
        if (cursoField.value) {
            inicializeFilters(cursoField.value);
        }

        cursoField.addEventListener("change", function (e) {
            inicializeFilters(e.target.value);
        });
    }
});
