import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import App from './App.vue'

// PrimeVue Components
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Dialog from 'primevue/dialog'
import Splitter from 'primevue/splitter'
import SplitterPanel from 'primevue/splitterpanel'
import Toolbar from 'primevue/toolbar'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import Toast from 'primevue/toast'
import ToastService from 'primevue/toastservice'
import 'primeicons/primeicons.css'

const app = createApp(App)

app.use(PrimeVue, {
  theme: {
    preset: Aura,
    options: {
      darkModeSelector: '.dark-mode'
    }
  }
})

app.use(ToastService)

// Register all PrimeVue components
app.component('DataTable', DataTable)
app.component('Column', Column)
app.component('Button', Button)
app.component('InputText', InputText)
app.component('Textarea', Textarea)
app.component('Dialog', Dialog)
app.component('Splitter', Splitter)
app.component('SplitterPanel', SplitterPanel)
app.component('Toolbar', Toolbar)
app.component('Card', Card)
app.component('Tag', Tag)
app.component('Toast', Toast)

app.mount('#app')
