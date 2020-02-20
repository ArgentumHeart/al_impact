rm -rf main_output_old
mv main_output main_output_old
echo 'pushed output back'
python3 main.py
cd main_output
pysph dump_vtk *.hdf5
cd ..
